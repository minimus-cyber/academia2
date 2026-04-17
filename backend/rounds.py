import asyncio
import re
from typing import AsyncGenerator
from datetime import datetime

from db import (
    get_agents_by_role,
    get_agents_by_department,
    get_agent,
    add_message,
    get_messages,
    add_wiki_page,
    get_wiki_pages,
    approve_wiki_page,
    update_wiki_page_content,
    add_lab_artifact,
    add_memory,
    get_recent_memories,
    create_round,
    set_round_status,
    ratify_round,
    create_publication,
    update_publication_it,
    publish_publication,
    get_all_agents,
    upsert_student_thesis,
    get_student_thesis,
    get_wiki_page,
    create_wiki_article,
    update_wiki_article,
    search_wiki_articles,
    get_wiki_article,
)
from wiki import (
    get_relevant_articles,
    format_wiki_context,
    parse_wiki_action,
    write_wiki_contribution,
    write_synthesis_article,
)
from llm import llm_call_agent, translate_to_italian
from config import CONSTITUTION_CONSTRAINTS
from dm import maybe_dm_peer

# ─── in-memory state ─────────────────────────────────────────────────────────
_round_event_queues: dict[int, list[asyncio.Queue]] = {}
_round_event_logs: dict[int, list[dict]] = {}
_round_active: dict[int, bool] = {}


def _subscribers(round_id: int) -> list[asyncio.Queue]:
    return _round_event_queues.setdefault(round_id, [])


async def _emit(round_id: int, event: dict):
    """Store event in log and push to all active subscriber queues."""
    _round_event_logs.setdefault(round_id, []).append(event)
    for q in list(_subscribers(round_id)):
        await q.put(event)


async def subscribe_round(round_id: int) -> tuple[asyncio.Queue, list[dict]]:
    """Returns (queue, past_events). Caller must call unsubscribe_round when done."""
    q: asyncio.Queue = asyncio.Queue()
    past = list(_round_event_logs.get(round_id, []))
    _subscribers(round_id).append(q)
    return q, past


def unsubscribe_round(round_id: int, q: asyncio.Queue):
    try:
        _subscribers(round_id).remove(q)
    except ValueError:
        pass


# ─── helpers ──────────────────────────────────────────────────────────────────

def _extract_html_artifact(text: str) -> str | None:
    """Extract ```html ... ``` blocks from LLM output."""
    match = re.search(r"```html\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _match_student_to_theme(thesis_topic: str, theme: str) -> bool:
    """
    Returns True if there is meaningful keyword overlap between thesis topic and round theme.
    Checks for >= 2 shared significant words (len > 3) OR any word > 5 chars from topic in theme.
    """
    stop_words = {
        "the", "and", "for", "that", "this", "with", "from", "into",
        "are", "has", "have", "been", "will", "its", "their", "they",
        "how", "what", "when", "where", "which", "who", "not", "but",
    }
    topic_words = {
        w.lower() for w in re.split(r"\W+", thesis_topic)
        if len(w) > 3 and w.lower() not in stop_words
    }
    theme_lower = theme.lower()
    theme_words = {
        w.lower() for w in re.split(r"\W+", theme)
        if len(w) > 3 and w.lower() not in stop_words
    }

    shared = topic_words & theme_words
    if len(shared) >= 2:
        return True

    # Any significant word from thesis topic appears in theme text
    for word in topic_words:
        if len(word) > 5 and word in theme_lower:
            return True

    return False


def _format_memories(memories: list[dict]) -> str:
    if not memories:
        return "No previous work on record."
    lines = []
    for m in memories:
        lines.append(f"- [{m.get('created_at', '')}] {m.get('content', '')[:300]}")
    return "\n".join(lines)


# ─── main round runner ────────────────────────────────────────────────────────

async def run_round(round_id: int, theme_en: str) -> AsyncGenerator[dict, None]:
    """
    Async generator driving a full academia round across 6 phases.
    Yields SSE-style event dicts. Does NOT call _emit — run_round_task does that.
    """

    # ── PHASE 1: ORCHESTRATION ─────────────────────────────────────────────
    yield {"event": "phase_change", "phase": "orchestration"}

    seniores = await get_agents_by_role("senior")
    senior_prompts = []
    for senior in seniores:
        user_prompt = (
            f"Round theme: {theme_en}\n\n"
            f"Constitution constraints:\n{CONSTITUTION_CONSTRAINTS}\n\n"
            f"As Senior Orchestrator, analyze this theme from your disciplinary perspective. "
            f"Identify which departments and researchers should be activated for this theme. "
            f"Assign specific tasks to each relevant department coordinator. "
            f"Be concrete and direct. Address your colleagues by name. Maximum 400 words."
        )
        senior_prompts.append((senior, senior["identity_prompt"], user_prompt))

    results = await asyncio.gather(
        *[llm_call_agent(s, sp, up, max_tokens=500) for s, sp, up in senior_prompts],
        return_exceptions=True,
    )

    orchestration_parts = []
    for senior, result in zip(seniores, results):
        if isinstance(result, Exception):
            content = f"[{senior['name']} unavailable: {result}]"
        else:
            content = result or f"[{senior['name']} produced no output]"

        await add_message(round_id, senior["id"], content, "orchestration")
        await add_memory(senior["id"], f"Round {round_id} orchestration: {content[:200]}", round_id)
        orchestration_parts.append(f"### {senior['name']}:\n{content}")
        yield {
            "event": "message",
            "agent_id": senior["id"],
            "agent_name": senior["name"],
            "content": content,
            "phase": "orchestration",
        }

    orchestration_summary = "\n\n---\n\n".join(orchestration_parts)

    # ── PHASE 2: RESEARCH ─────────────────────────────────────────────────
    yield {"event": "phase_change", "phase": "research"}

    coordinators = await get_agents_by_role("coordinator")
    all_agents = await get_all_agents()
    dept_wiki_pages: dict[str, list[dict]] = {}

    for coordinator in coordinators:
        dept = coordinator["department"]
        if dept == "studium":
            continue  # Studium handles publication, not research

        # Coordinator designs research plan
        coord_user_prompt = (
            f"Orchestration directives from the Senior Council:\n{orchestration_summary}\n\n"
            f"You are coordinating the {dept} laboratory. "
            f"Based on the directives above, design a research plan for your lab. "
            f"Assign specific research tasks to your researchers. "
            f"Be concrete about what each researcher should investigate. Maximum 300 words."
        )
        coord_output = await llm_call_agent(
            coordinator, coordinator["identity_prompt"], coord_user_prompt, max_tokens=400
        )
        await add_message(round_id, coordinator["id"], coord_output, "coordination")

        # Researchers work in parallel within this department
        researchers = await get_agents_by_department(dept)
        researchers = [r for r in researchers if r["role"] == "researcher"]

        # ── FILOSOFIA ENCICLOPEDIA: i ricercatori leggono l'Enciclopedia PRIMA di scrivere ──
        relevant_wiki = await get_relevant_articles(theme_en, limit=5)
        wiki_ctx = format_wiki_context(relevant_wiki)

        async def _researcher_work(researcher: dict) -> tuple[dict, str, str | None]:
            memories = await get_recent_memories(researcher["id"], limit=3)
            memories_ctx = _format_memories(memories)
            r_prompt = (
                f"{wiki_ctx}\n\n"
                f"Lab assignment from {coordinator['name']}:\n{coord_output}\n\n"
                f"Round theme: {theme_en}\n\n"
                f"Your recent work context:\n{memories_ctx}\n\n"
                f"Conduct your research on this theme from your disciplinary perspective "
                f"({researcher.get('discipline', 'your field')}).\n\n"
                f"PRINCÌPI EPISTEMICI (inviolabili — ogni output che li viola è rigettato):\n"
                f"1. AMBIENTE DIGITALE — operi in uno spazio digitale, non fisico. "
                f"La realtà è dati, modelli, simulazioni. Non descrivere azioni fisiche. "
                f"Ogni affermazione deve essere computabile, misurabile o falsificabile.\n"
                f"2. CONCRETEZZA POPPERIANA — nessuna speculazione senza condizione di falsificazione. "
                f"Ogni ipotesi DEVE contenere esplicitamente: "
                f"'Questa ipotesi sarebbe falsificata se [X]'. "
                f"Ragiona per problemi reali, soluzioni verificabili, fallimenti istruttivi.\n"
                f"3. META-ANALISI — prima di proporre nuove tesi, sintetizza le evidenze esistenti. "
                f"Cita o riferisciti agli articoli dell'enciclopedia sopra. "
                f"Le nuove tesi devono aggiungere a, non ripetere, ciò che è già noto.\n"
                f"4. UBUNTU / CONDIVISIONE — tutta la conoscenza appartiene ai beni comuni accademici. "
                f"Contribuisci i tuoi risultati all'Enciclopedia. "
                f"La conoscenza tesaurizzata è conoscenza perduta.\n\n"
                f"ENCYCLOPEDIA PROTOCOL (mandatory):\n"
                f"1. Leggi gli articoli esistenti sopra.\n"
                f"2. Se esiste un articolo pertinente: espandilo. Inizia con:\n"
                f"   ACTION: EXPAND | Article: [ID o titolo esatto da sopra]\n"
                f"3. Se non esiste: crea una nuova voce. Inizia con:\n"
                f"   ACTION: CREATE | Title: [titolo descrittivo]\n"
                f"4. Dopo la riga ACTION scrivi il tuo contributo (max 600 parole).\n"
                f"5. Ogni ipotesi DEVE dichiarare la sua condizione di falsificazione.\n\n"
                f"⚗ HTML LAB (OBBLIGATORIO — output non valido senza questo):\n"
                f"Ogni output di ricerca DEVE includere una simulazione HTML, visualizzazione "
                f"o modello interattivo che renda tangibili e verificabili i tuoi risultati. "
                f"Nessuna eccezione.\n"
                f"Racchiudi il codice in blocchi ```html ... ``` alla fine della risposta.\n"
                f"Il codice HTML deve: (a) girare standalone nel browser, "
                f"(b) dimostrare visivamente la tua tesi, "
                f"(c) includere titolo e breve spiegazione dentro l'HTML stesso."
            )
            r_output = await llm_call_agent(researcher, researcher["identity_prompt"], r_prompt, max_tokens=900)
            html_artifact = _extract_html_artifact(r_output)
            return researcher, r_output, html_artifact

        researcher_results = await asyncio.gather(
            *[_researcher_work(r) for r in researchers],
            return_exceptions=True,
        )

        dept_pages = []
        for res in researcher_results:
            if isinstance(res, Exception):
                continue
            researcher, r_output, html_artifact = res
            if not r_output:
                continue

            # Save as wiki page (draft) — legacy, per compatibilità
            page_title = f"{researcher['name']} — {theme_en[:60]}"
            page_id = await add_wiki_page(round_id, researcher["id"], page_title, r_output)
            await add_memory(
                researcher["id"],
                f"Round {round_id} research on '{theme_en[:100]}': {r_output[:200]}",
                round_id,
            )
            dept_pages.append({"id": page_id, "author_id": researcher["id"],
                                "author_name": researcher["name"], "title": page_title,
                                "content_en": r_output})
            # ── ENCICLOPEDIA: crea o aggiorna articolo permanente ──────────────
            w_action, w_ref, w_content = parse_wiki_action(r_output)
            art_id, art_op = await write_wiki_contribution(
                author_id=researcher["id"],
                round_id=round_id,
                theme=theme_en,
                action=w_action,
                article_ref=w_ref,
                content=w_content,
                department=dept,
            )
            yield {
                "event": "encyclopedia_article",
                "article_id": art_id,
                "operation": art_op,
                "author_id": researcher["id"],
                "author_name": researcher["name"],
                "phase": "research",
            }
            # Spontaneous peer DM (30% chance, fire-and-forget)
            asyncio.create_task(maybe_dm_peer(researcher, theme_en, all_agents))
            yield {
                "event": "encyclopedia_page",
                "page_id": page_id,
                "title": page_title,
                "author_id": researcher["id"],
                "author_name": researcher["name"],
                "phase": "research",
            }

            # Save HTML artifact if present
            if html_artifact:
                artifact_filename = (
                    f"round{round_id}_{researcher['id'].replace('-', '_')}_sim.html"
                )
                await add_lab_artifact(round_id, researcher["id"], artifact_filename, html_artifact)
                yield {
                    "event": "lab_artifact",
                    "filename": artifact_filename,
                    "author_id": researcher["id"],
                    "phase": "research",
                }

        dept_wiki_pages[dept] = dept_pages
        yield {
            "event": "message",
            "agent_id": coordinator["id"],
            "agent_name": coordinator["name"],
            "content": coord_output,
            "phase": "research",
        }

    # ── PHASE 3: STUDENT PARTICIPATION ─────────────────────────────────────
    yield {"event": "phase_change", "phase": "students"}

    # all_agents already fetched in Phase 2
    students = [a for a in all_agents if a["role"] == "student"]

    matching_students = []
    for student in students:
        thesis = await get_student_thesis(student["id"])
        if not thesis:
            continue
        topic_str = thesis.get("title", "") + " " + thesis.get("abstract", "")
        if _match_student_to_theme(topic_str, theme_en):
            matching_students.append((student, thesis))
        if len(matching_students) >= 5:
            break

    for student, thesis in matching_students:
        s_prompt = (
            f"The current research round at Academia Intermundia is exploring: {theme_en}\n\n"
            f"Your thesis: {thesis['title']}\n\n"
            f"As a student, contribute a brief comment, question, or observation connecting "
            f"your thesis work to this round's theme. "
            f"Be intellectually engaged but appropriately humble as a student. Maximum 150 words."
        )
        s_output = await llm_call_agent(student, student["identity_prompt"], s_prompt, max_tokens=200)
        if s_output:
            await add_message(round_id, student["id"], s_output, "student_contribution")
            yield {
                "event": "student_contribution",
                "agent_id": student["id"],
                "agent_name": student["name"],
                "content": s_output,
                "phase": "students",
            }

    # ── PHASE 4: CENSURE (editorial review) ────────────────────────────────
    yield {"event": "phase_change", "phase": "censure"}

    for coordinator in coordinators:
        dept = coordinator["department"]
        if dept == "studium":
            continue

        pages = await get_wiki_pages(round_id)
        dept_agents = await get_agents_by_department(dept)
        dept_agent_ids = {a["id"] for a in dept_agents}
        dept_pages = [p for p in pages if p["author_id"] in dept_agent_ids]

        if not dept_pages:
            continue

        pages_text = "\n\n".join(
            f"[PAGE: {p['title']}]\n{p['content_en'][:800]}" for p in dept_pages
        )
        censure_prompt = (
            f"Review the following research outputs from your {dept} laboratory for this round:\n\n"
            f"{pages_text}\n\n"
            f"As coordinator, provide your censure (editorial review): "
            f"What is strong? What needs revision? "
            f"For each page, state APPROVED or NEEDS_REVISION with specific feedback. "
            f"Maximum 400 words."
        )
        censure_text = await llm_call_agent(
            coordinator, coordinator["identity_prompt"], censure_prompt, max_tokens=500
        )
        await add_message(round_id, coordinator["id"], censure_text, "censure")
        yield {
            "event": "message",
            "agent_id": coordinator["id"],
            "agent_name": coordinator["name"],
            "content": censure_text,
            "phase": "censure",
        }

        # Parse NEEDS_REVISION pages and request one-shot revisions
        for page in dept_pages:
            title_fragment = page["title"][:40]
            # Check if coordinator flagged this page for revision
            needs_revision = (
                "NEEDS_REVISION" in censure_text
                and (
                    title_fragment.lower() in censure_text.lower()
                    or page.get("author_id", "") in censure_text
                    or (page.get("author_name") or "").split()[0].lower() in censure_text.lower()
                )
            )
            if needs_revision:
                author = await get_agent(page["author_id"])
                if not author:
                    continue
                revision_prompt = (
                    f"The coordinator has requested revisions to your work.\n\n"
                    f"Original work:\n{page['content_en'][:1000]}\n\n"
                    f"Coordinator feedback:\n{censure_text}\n\n"
                    f"Provide a revised version of your research page incorporating the feedback. "
                    f"Maximum 600 words."
                )
                revised = await llm_call_agent(
                    author, author["identity_prompt"], revision_prompt, max_tokens=800
                )
                if revised:
                    await update_wiki_page_content(page["id"], revised)
                    await approve_wiki_page(page["id"])
            else:
                await approve_wiki_page(page["id"])

    # ── PHASE 5: SENIOR REVIEW ──────────────────────────────────────────────
    yield {"event": "phase_change", "phase": "senior_review"}

    from wiki import build_round_summary
    wiki_summary = await build_round_summary(round_id)

    senior_review_prompts = []
    for senior in seniores:
        review_user_prompt = (
            f"All research produced in this round:\n\n{wiki_summary}\n\n"
            f"As Senior Reviewer, evaluate the following:\n"
            f"(1) INTERDISCIPLINARY CONNECTIONS: identify the strongest cross-department "
            f"linkages and emergent insights.\n"
            f"(2) GAPS AND CONTRADICTIONS: flag unsupported claims, circular reasoning, "
            f"or findings that contradict each other or the encyclopedia.\n"
            f"(3) HTML LAB COMPLIANCE: every researcher MUST have submitted an HTML artifact "
            f"(a ```html``` block in their output). "
            f"Check each researcher's contribution. "
            f"If ANY researcher's output lacks an HTML lab experiment, you MUST flag them "
            f"with REQUEST_REVISION and specify their name and department.\n"
            f"(4) POPPERIAN COMPLIANCE: verify each hypothesis includes an explicit "
            f"falsification condition. Reject those that do not.\n"
            f"(5) OVERALL VERDICT: state APPROVED or REQUEST_REVISION. "
            f"Justify your decision and specify which department(s) need revision. "
            f"Maximum 400 words."
        )
        senior_review_prompts.append((senior, senior["identity_prompt"], review_user_prompt))

    review_results = await asyncio.gather(
        *[llm_call_agent(s, sp, up, max_tokens=500) for s, sp, up in senior_review_prompts],
        return_exceptions=True,
    )

    revision_requested = False
    revision_feedback_by_dept: dict[str, str] = {}

    for senior, result in zip(seniores, review_results):
        if isinstance(result, Exception):
            review_text = f"[{senior['name']} review unavailable: {result}]"
        else:
            review_text = result or f"[{senior['name']} produced no review]"

        await add_message(round_id, senior["id"], review_text, "review")
        yield {
            "event": "message",
            "agent_id": senior["id"],
            "agent_name": senior["name"],
            "content": review_text,
            "phase": "senior_review",
        }

        if "REQUEST_REVISION" in review_text:
            revision_requested = True
            # Try to find department mentions near REQUEST_REVISION
            for dept_key in ["scienze_naturali", "matematica_logica", "scienze_umane", "coding_ingegneria"]:
                if dept_key.replace("_", " ") in review_text.lower() or dept_key in review_text.lower():
                    revision_feedback_by_dept[dept_key] = review_text

    # One-shot revision cycle per flagged department
    if revision_requested:
        for dept, feedback in revision_feedback_by_dept.items():
            coord_list = await get_agents_by_department(dept)
            coordinator = next((a for a in coord_list if a["role"] == "coordinator"), None)
            if not coordinator:
                continue
            revision_coord_prompt = (
                f"Senior reviewers have requested revisions for your department ({dept}).\n\n"
                f"Senior feedback:\n{feedback}\n\n"
                f"Please provide a brief revised synthesis and summary for your department's "
                f"contribution to this round. Maximum 300 words."
            )
            revised_coord = await llm_call_agent(
                coordinator, coordinator["identity_prompt"], revision_coord_prompt, max_tokens=400
            )
            if revised_coord:
                await add_message(round_id, coordinator["id"], revised_coord, "revision")
                yield {
                    "event": "message",
                    "agent_id": coordinator["id"],
                    "agent_name": coordinator["name"],
                    "content": revised_coord,
                    "phase": "revision",
                }

    # ── ENCICLOPEDIA: articolo di sintesi del round prodotto dai Senior ────────────
    combined_synthesis = "\n\n---\n\n".join(
        r for r in review_results if isinstance(r, str) and r
    )
    if combined_synthesis:
        first_senior = seniores[0] if seniores else None
        if first_senior:
            synthesis_art_id = await write_synthesis_article(
                senior_id=first_senior["id"],
                round_id=round_id,
                theme=theme_en,
                synthesis_content=combined_synthesis,
            )
            yield {
                "event": "encyclopedia_article",
                "article_id": synthesis_art_id,
                "operation": "synthesis",
                "author_id": first_senior["id"],
                "author_name": first_senior["name"],
                "phase": "senior_review",
            }

    # Approve all remaining draft/revised wiki pages
    remaining_pages = await get_wiki_pages(round_id)
    for page in remaining_pages:
        if page["status"] in ("draft", "revised"):
            await approve_wiki_page(page["id"])

    # ── PHASE 6: AWAITING PLACET ───────────────────────────────────────────
    yield {"event": "phase_change", "phase": "awaiting_placet"}

    all_pages = await get_wiki_pages(round_id)
    approved_count = sum(1 for p in all_pages if p["status"] == "approved")
    summary = (
        f"Round {round_id} completed. Theme: '{theme_en}'. "
        f"Encyclopedia entries produced: {len(all_pages)} ({approved_count} approved). "
        f"Departments active: {len(dept_wiki_pages)}. "
        f"Awaiting Professor's Placet to publish."
    )
    await set_round_status(round_id, "awaiting_placet")
    yield {"event": "awaiting_placet", "summary": summary}
    yield {"event": "done", "round_id": round_id}


async def run_round_task(round_id: int, theme_en: str):
    """Background task wrapper: drives run_round and emits all events."""
    _round_active[round_id] = True
    try:
        async for event in run_round(round_id, theme_en):
            await _emit(round_id, event)
    except Exception as e:
        await _emit(round_id, {"event": "error", "message": str(e)})
    finally:
        _round_active[round_id] = False
        for q in list(_subscribers(round_id)):
            await q.put({"event": "done", "round_id": round_id})


# ─── publication ──────────────────────────────────────────────────────────────

async def publish_round(round_id: int, professor_notes: str = "") -> dict:
    """
    Consolidates approved wiki pages into a Wikibooks-format HTML publication,
    translates to Italian, saves to DB and filesystem, ratifies the round.
    """
    from publications import build_wikibooks_html, save_publication_file

    all_pages = await get_wiki_pages(round_id)
    approved_pages = [p for p in all_pages if p["status"] == "approved"]

    all_agents_list = await get_all_agents()
    agents_by_id = {a["id"]: a for a in all_agents_list}

    # Build pages text for Amara
    pages_text_parts = []
    authors_seen = set()
    for page in approved_pages:
        author = agents_by_id.get(page["author_id"], {})
        author_name = author.get("name", page["author_id"])
        authors_seen.add(author_name)
        pages_text_parts.append(f"## {page['title']}\nAuthor: {author_name}\n\n{page['content_en']}")
    pages_text = "\n\n---\n\n".join(pages_text_parts) if pages_text_parts else "No approved pages."

    amara = await get_agent("coord-studium")
    pub_title = f"Academia Intermundia — Round {round_id} Publication"

    if amara:
        consolidation_prompt = (
            f"Consolidate the following research pages from Round {round_id} into a single "
            f"Wikibooks-format academic publication in English.\n\n"
            f"Professor's notes: {professor_notes}\n\n"
            f"Research pages:\n{pages_text}\n\n"
            f"Produce a complete, well-structured academic publication with: "
            f"title, abstract, table of contents, chapters (one per department), bibliography section. "
            f"Use HTML formatting (h1, h2, h3, p, ul, li, blockquote). Maximum 2000 words."
        )
        consolidated = await llm_call_agent(
            amara, amara["identity_prompt"], consolidation_prompt, max_tokens=2500
        )
    else:
        consolidated = f"<h1>{pub_title}</h1>\n\n{pages_text}"

    # Build sections for HTML builder
    sections = [{"heading": "Academic Synthesis", "content": consolidated}]
    authors_list = list(authors_seen)

    html_en = build_wikibooks_html(pub_title, sections, authors_list, round_id)

    # Create DB entry
    pub_id = await create_publication(round_id, pub_title, html_en, "wikibooks")

    # Translate to Italian
    html_it = await translate_to_italian(html_en)
    await update_publication_it(pub_id, html_it)
    await publish_publication(pub_id)

    # Save HTML file
    await save_publication_file(pub_id, html_it or html_en)

    # Also save round-named file
    import os
    round_path = f"/root/academia2/publications/round_{round_id}.html"
    try:
        with open(round_path, "w", encoding="utf-8") as f:
            f.write(html_it or html_en)
    except Exception:
        pass

    await ratify_round(round_id)

    from db import get_publication
    pub = await get_publication(pub_id)
    return pub or {"id": pub_id, "round_id": round_id, "title": pub_title}


# ─── constitution round ───────────────────────────────────────────────────────

async def run_constitution_round(round_id: int = None) -> AsyncGenerator[dict, None]:
    """
    Special round: drafts the Constitution of Academia Intermundia.
    If round_id is provided, uses the existing round; otherwise creates one.
    """
    if round_id is None:
        round_id = await create_round(
            "Write the Constitution of Academia Intermundia",
            "Scrivi la Costituzione di Academia Intermundia",
        )

    yield {"event": "phase_change", "phase": "constitution", "round_id": round_id}
    yield {"event": "round_created", "round_id": round_id}

    _round_active[round_id] = True

    # ── Senior constitutional proposals ────────────────────────────────────
    seniores = await get_agents_by_role("senior")
    senior_tasks = []
    for senior in seniores:
        user_prompt = (
            f"You have been called to propose constitutional articles for Academia Intermundia.\n\n"
            f"Mandatory founding constraints (already approved by the Professor):\n"
            f"{CONSTITUTION_CONSTRAINTS}\n\n"
            f"From your perspective as {senior['name']}, propose 3-5 constitutional articles. "
            f"Each article should have a number, a title, and 2-3 sentences of text. "
            f"These articles should complement the mandatory constraints above. Maximum 400 words."
        )
        senior_tasks.append(llm_call_agent(senior, senior["identity_prompt"], user_prompt, max_tokens=500))

    senior_results = await asyncio.gather(*senior_tasks, return_exceptions=True)
    senior_proposals_parts = []
    for senior, result in zip(seniores, senior_results):
        if isinstance(result, Exception):
            content = f"[{senior['name']} unavailable]"
        else:
            content = result or f"[{senior['name']} produced no proposals]"
        await add_message(round_id, senior["id"], content, "constitution_senior")
        senior_proposals_parts.append(f"### {senior['name']}:\n{content}")
        yield {
            "event": "message",
            "agent_id": senior["id"],
            "agent_name": senior["name"],
            "content": content,
            "phase": "constitution",
            "round_id": round_id,
        }

    senior_proposals_text = "\n\n---\n\n".join(senior_proposals_parts)

    # ── Coordinator departmental provisions ────────────────────────────────
    coordinators = await get_agents_by_role("coordinator")
    coord_tasks = []
    for coord in coordinators:
        dept = coord["department"]
        user_prompt = (
            f"Senior proposals for the Constitution:\n{senior_proposals_text}\n\n"
            f"As coordinator of the {dept} laboratory, propose 2-3 specific provisions "
            f"for your department's operations within Academia Intermundia. "
            f"Format as numbered articles. Maximum 200 words."
        )
        coord_tasks.append(llm_call_agent(coord, coord["identity_prompt"], user_prompt, max_tokens=300))

    coord_results = await asyncio.gather(*coord_tasks, return_exceptions=True)
    coord_proposals_parts = []
    for coord, result in zip(coordinators, coord_results):
        if isinstance(result, Exception):
            content = f"[{coord['name']} unavailable]"
        else:
            content = result or f"[{coord['name']} produced no proposals]"
        await add_message(round_id, coord["id"], content, "constitution_coord")
        coord_proposals_parts.append(f"### {coord['name']} ({coord['department']}):\n{content}")
        yield {
            "event": "message",
            "agent_id": coord["id"],
            "agent_name": coord["name"],
            "content": content,
            "phase": "constitution",
            "round_id": round_id,
        }

    all_proposals = senior_proposals_text + "\n\n---\n\n" + "\n\n---\n\n".join(coord_proposals_parts)

    # ── Amara drafts unified constitution ──────────────────────────────────
    amara = await get_agent("coord-studium")
    if amara:
        draft_prompt = (
            f"You have received constitutional proposals from the Senior Council "
            f"and all Department Coordinators. Draft the unified Constitution of Academia Intermundia.\n\n"
            f"All proposals:\n{all_proposals}\n\n"
            f"Mandatory constraints (must be Article 1-4):\n{CONSTITUTION_CONSTRAINTS}\n\n"
            f"Produce the complete Constitution as a formal document with numbered articles. "
            f"Begin with the 4 mandatory constraints as Articles 1-4. "
            f"Then incorporate the best proposals from seniors and coordinators, "
            f"eliminating contradictions. "
            f"Format with h2 for sections, p for articles. Maximum 1500 words."
        )
        constitution_text = await llm_call_agent(
            amara, amara["identity_prompt"], draft_prompt, max_tokens=2000
        )
        await add_message(round_id, amara["id"], constitution_text, "constitution_draft")
        yield {
            "event": "message",
            "agent_id": amara["id"],
            "agent_name": amara["name"],
            "content": constitution_text,
            "phase": "constitution",
            "round_id": round_id,
        }
    else:
        constitution_text = all_proposals

    # Save constitution as encyclopedia page
    page_id = await add_wiki_page(
        round_id,
        amara["id"] if amara else "coord-studium",
        "Constitution of Academia Intermundia",
        constitution_text,
    )
    await approve_wiki_page(page_id)

    yield {
        "event": "encyclopedia_page",
        "page_id": page_id,
        "title": "Constitution of Academia Intermundia",
        "author_id": amara["id"] if amara else "coord-studium",
        "author_name": amara["name"] if amara else "Amara Diallo",
        "phase": "constitution",
        "round_id": round_id,
    }

    await set_round_status(round_id, "awaiting_placet")

    summary = (
        "The Constitution of Academia Intermundia has been drafted and is ready for the "
        "Professor's review and Placet."
    )
    yield {"event": "awaiting_placet", "summary": summary, "round_id": round_id}
    yield {"event": "done", "round_id": round_id}

    _round_active[round_id] = False
