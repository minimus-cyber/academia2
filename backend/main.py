import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional

import aiosqlite

from config import ACADEMIA_VERSION, DB_PATH
from db import (
    init_db,
    get_all_agents,
    get_agent,
    get_all_rounds,
    get_round,
    get_messages,
    get_wiki_pages,
    get_all_wiki_pages,
    get_wiki_page,
    get_all_publications,
    get_publication,
    get_lab_artifacts,
    create_round,
    count_agents,
    set_round_status,
    init_dm_table,
    create_dm,
    get_dm_thread,
    get_dm_conversations,
    mark_dm_read,
    get_all_wiki_articles,
    get_wiki_article,
    get_wiki_article_revisions,
    get_wiki_article_links,
    get_wiki_articles_by_round,
    search_wiki_articles,
)
from agents import seed_agents
from rounds import (
    run_round_task,
    publish_round,
    run_constitution_round,
    subscribe_round,
    unsubscribe_round,
    _round_active,
    _round_event_logs,
    _emit,
)
from wiki import get_wiki_pages_by_round, search_wiki
from publications import list_publications_all, get_publication_detail
from translation import translate_input
from dm import _dm_subscribers, emit_dm, dao_dm_reply, notify_weinrot_dm


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_dm_table()
    async with aiosqlite.connect(DB_PATH) as db:
        await seed_agents(db)
    yield


app = FastAPI(title="Academia Intermundia", version=ACADEMIA_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ──────────────────────────────────────────────────────────

class StartRoundRequest(BaseModel):
    theme_it: str


class PlacetRequest(BaseModel):
    notes: Optional[str] = ""


class RevisionRequest(BaseModel):
    notes: str = "Please revise."


class DMRequest(BaseModel):
    from_id: str
    to_id: str
    content: str


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    n = await count_agents()
    return {"status": "ok", "version": ACADEMIA_VERSION, "agents": n}


@app.get("/agents")
async def list_agents():
    return await get_all_agents()


@app.get("/agents/{agent_id}")
async def agent_detail(agent_id: str):
    agent = await get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.get("/rounds")
async def list_rounds():
    return await get_all_rounds()


@app.get("/rounds/{round_id}")
async def round_detail(round_id: int):
    r = await get_round(round_id)
    if not r:
        raise HTTPException(status_code=404, detail="Round not found")
    messages = await get_messages(round_id)
    pages = await get_wiki_pages_by_round(round_id)
    return {**r, "messages": messages, "encyclopedia_pages": pages}


@app.post("/rounds/start")
async def start_round(body: StartRoundRequest, background_tasks: BackgroundTasks):
    theme_en = await translate_input(body.theme_it)
    round_id = await create_round(theme_en, body.theme_it)
    background_tasks.add_task(run_round_task, round_id, theme_en)
    return {
        "round_id": round_id,
        "theme_en": theme_en,
        "theme_it": body.theme_it,
    }


@app.get("/rounds/{round_id}/stream")
async def stream_round(round_id: int):
    r = await get_round(round_id)
    if not r:
        raise HTTPException(status_code=404, detail="Round not found")

    async def event_generator():
        q, past_events = await subscribe_round(round_id)
        try:
            # Replay past events to the new subscriber
            for event in past_events:
                yield f"data: {json.dumps(event)}\n\n"

            # If round already finished and we've replayed all events, stop
            if not _round_active.get(round_id, False) and past_events:
                yield f"data: {json.dumps({'event': 'done', 'round_id': round_id})}\n\n"
                return

            # Stream live events
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("event") in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'event': 'heartbeat'})}\n\n"
        finally:
            unsubscribe_round(round_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/rounds/{round_id}/placet")
async def give_placet(round_id: int, body: PlacetRequest, background_tasks: BackgroundTasks):
    r = await get_round(round_id)
    if not r:
        raise HTTPException(status_code=404, detail="Round not found")
    if r["status"] not in ("awaiting_placet", "active"):
        raise HTTPException(
            status_code=400,
            detail=f"Round status is '{r['status']}', cannot give placet",
        )
    background_tasks.add_task(_do_publish, round_id, body.notes or "")
    return {"message": "Placet received. Publication in progress.", "round_id": round_id}


@app.post("/rounds/{round_id}/revision")
async def request_revision(round_id: int, body: RevisionRequest, background_tasks: BackgroundTasks):
    """Professor requests a revision of a round. Marks it rejected and starts a new round
    with the same theme + professor notes injected as context."""
    r = await get_round(round_id)
    if not r:
        raise HTTPException(status_code=404, detail="Round not found")
    if r["status"] not in ("awaiting_placet", "active"):
        raise HTTPException(
            status_code=400,
            detail=f"Round status is '{r['status']}', cannot request revision",
        )
    # Mark original round as rejected
    await set_round_status(round_id, "rejected")
    # Build new round incorporating professor feedback in both languages
    prof_note = f"[PROFESSOR REVISION: {body.notes}]"
    revision_theme_en = f"{r['theme_en']} {prof_note}"
    revision_theme_it = f"{r['theme_it']} {prof_note}"
    new_round_id = await create_round(revision_theme_en, revision_theme_it)
    background_tasks.add_task(run_round_task, new_round_id, revision_theme_en)
    await _emit(round_id, {"event": "revision_requested", "new_round_id": new_round_id})
    return {"message": "Revision round started.", "original_round_id": round_id, "new_round_id": new_round_id}


async def _do_publish(round_id: int, notes: str):
    pub = await publish_round(round_id, notes)
    await _emit(round_id, {
        "event": "published",
        "publication_id": pub.get("id") if pub else None,
        "round_id": round_id,
    })


# ── Direct Messaging endpoints ────────────────────────────────────────────────

@app.get("/dm/stream/{participant_id}")
async def dm_stream(participant_id: str):
    q = asyncio.Queue()
    _dm_subscribers.setdefault(participant_id, []).append(q)

    async def gen():
        try:
            while True:
                msg = await q.get()
                yield f"data: {json.dumps(msg)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            try:
                _dm_subscribers[participant_id].remove(q)
            except (ValueError, KeyError):
                pass

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/dm/conversations/{participant_id}")
async def list_conversations(participant_id: str):
    convs = await get_dm_conversations(participant_id)
    all_agents = await get_all_agents()
    agent_map = {a["id"]: a for a in all_agents}
    agent_map["professor"] = {"id": "professor", "name": "The Professor", "role": "professor", "symbol": "🎓"}
    agent_map["weinrot"] = {"id": "weinrot", "name": "Weinrot", "role": "orchestrator", "symbol": "🍷"}
    for c in convs:
        other = c.get("other", "")
        a = agent_map.get(other, {})
        c["other_name"] = a.get("name", other)
        c["other_symbol"] = a.get("symbol", "🤖")
        c["other_role"] = a.get("role", "")
    return convs


@app.get("/dm/thread/{participant_a}/{participant_b}")
async def get_thread(participant_a: str, participant_b: str):
    await mark_dm_read(participant_a, participant_b)
    return await get_dm_thread(participant_a, participant_b)


@app.post("/dm/send")
async def send_dm(body: DMRequest, background_tasks: BackgroundTasks):
    SYSTEM_PARTICIPANTS = {"professor", "weinrot"}
    if body.from_id not in SYSTEM_PARTICIPANTS:
        agent = await get_agent(body.from_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Sender '{body.from_id}' not found")
    if body.to_id not in SYSTEM_PARTICIPANTS:
        agent = await get_agent(body.to_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Recipient '{body.to_id}' not found")

    dm_id = await create_dm(body.from_id, body.to_id, body.content)
    payload = {"id": dm_id, "from_id": body.from_id, "to_id": body.to_id,
               "content": body.content, "created_at": "now"}
    await emit_dm(body.to_id, payload)
    await emit_dm(body.from_id, payload)  # also notify sender's SSE stream

    if body.to_id not in SYSTEM_PARTICIPANTS:
        background_tasks.add_task(dao_dm_reply, body.to_id, body.from_id, body.content)
    elif body.to_id == "professor":
        background_tasks.add_task(notify_weinrot_dm, body.from_id, body.content)

    return {"id": dm_id, "status": "sent"}


@app.post("/rounds/constitution")
async def start_constitution(background_tasks: BackgroundTasks):
    """
    Starts the constitution round as a background task.
    Creates the round immediately and returns its ID.
    """
    # Pre-create round so we can return round_id immediately
    round_id = await create_round(
        "Write the Constitution of Academia Intermundia",
        "Scrivi la Costituzione di Academia Intermundia",
    )

    async def _run_constitution(rid: int):
        _round_active[rid] = True
        try:
            async for event in run_constitution_round(rid):
                emit_rid = event.get("round_id", rid)
                await _emit(emit_rid, event)
        except Exception as e:
            await _emit(rid, {"event": "error", "message": str(e)})
        finally:
            _round_active[rid] = False

    background_tasks.add_task(_run_constitution, round_id)
    return {"message": "Constitution round started", "round_id": round_id}


@app.get("/rounds/{round_id}/stream/constitution")
async def stream_constitution(round_id: int):
    # Same SSE endpoint as regular rounds
    return await stream_round(round_id)


@app.get("/encyclopedia")
async def list_encyclopedia():
    return await get_all_wiki_pages()


@app.get("/encyclopedia/search")
async def encyclopedia_search(q: str):
    return await search_wiki(q)




# ── Enciclopedia — articoli permanenti (filosofia Wikipedia) ──────────────────

@app.get("/encyclopedia/articles")
async def list_encyclopedia_articles():
    """Tutti gli articoli permanenti dell'Enciclopedia, ordinati per ultimo aggiornamento."""
    return await get_all_wiki_articles(limit=200)


@app.get("/encyclopedia/articles/search")
async def search_encyclopedia_articles_api(q: str):
    """Ricerca full-text sugli articoli permanenti dell'Enciclopedia."""
    return await search_wiki_articles(q, limit=30)


@app.get("/encyclopedia/articles/{article_id}")
async def encyclopedia_article_detail(article_id: int):
    """Dettaglio articolo Enciclopedia con contenuto completo."""
    article = await get_wiki_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    links = await get_wiki_article_links(article_id)
    return {**article, "linked_articles": links}


@app.get("/encyclopedia/articles/{article_id}/revisions")
async def encyclopedia_article_revisions(article_id: int):
    """Cronologia completa delle revisioni di un articolo Enciclopedia."""
    article = await get_wiki_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    revisions = await get_wiki_article_revisions(article_id)
    return {"article": article, "revisions": revisions}


@app.get("/encyclopedia/articles/{article_id}/links")
async def encyclopedia_article_links_api(article_id: int):
    """Articoli linkati da questo articolo (outbound cross-references)."""
    article = await get_wiki_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return await get_wiki_article_links(article_id)
@app.get("/encyclopedia/{page_id}")
async def encyclopedia_page(page_id: int):
    page = await get_wiki_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


@app.get("/rounds/{round_id}/encyclopedia-articles")
async def round_encyclopedia_articles(round_id: int):
    """Articoli permanenti creati o aggiornati durante questo round."""
    return await get_wiki_articles_by_round(round_id)


@app.get("/publications")
async def list_pubs():
    return await list_publications_all()


@app.get("/publications/{pub_id}")
async def pub_detail(pub_id: int):
    pub = await get_publication_detail(pub_id)
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")
    return pub


@app.get("/publications/{pub_id}/html")
async def pub_html(pub_id: int):
    pub = await get_publication_detail(pub_id)
    if not pub:
        raise HTTPException(status_code=404)
    html = pub.get("content_it_html") or pub.get("content_en_html") or "<p>No content</p>"
    return HTMLResponse(content=html)


@app.get("/labs/{round_id}")
async def lab_artifacts(round_id: int):
    return await get_lab_artifacts(round_id)
