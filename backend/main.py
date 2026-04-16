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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
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
    return {**r, "messages": messages, "wiki_pages": pages}


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


async def _do_publish(round_id: int, notes: str):
    pub = await publish_round(round_id, notes)
    await _emit(round_id, {
        "event": "published",
        "publication_id": pub.get("id") if pub else None,
        "round_id": round_id,
    })


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
            async for event in run_constitution_round():
                # The generator creates its own round, so we emit to the
                # round_id found in each event (or the pre-created one)
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


@app.get("/wiki")
async def list_wiki():
    return await get_all_wiki_pages()


@app.get("/wiki/search")
async def wiki_search(q: str):
    return await search_wiki(q)


@app.get("/wiki/{page_id}")
async def wiki_page(page_id: int):
    page = await get_wiki_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


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
