import re
from db import (
    get_wiki_pages, get_agent, get_all_wiki_pages, get_wiki_page,
    search_wiki_articles, get_all_wiki_articles, get_wiki_article,
    get_wiki_article_revisions, create_wiki_article, update_wiki_article,
    get_wiki_article_links, get_wiki_articles_by_round, get_db,
)


# ── Slug ──────────────────────────────────────────────────────────────────────

def build_article_slug(title: str) -> str:
    """Converte titolo in slug URL-safe."""
    s = title.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:100]


# ── Pre-research context ───────────────────────────────────────────────────────

async def get_relevant_articles(theme: str, limit: int = 5) -> list[dict]:
    """
    Trova articoli dell'Enciclopedia esistenti rilevanti per il tema corrente.
    Usato per iniettare contesto nei ricercatori PRIMA che scrivano.
    Filosofia: i DAO devono sapere cosa esiste già prima di contribuire.
    """
    # Estrai parole significative (> 4 caratteri)
    words = [w for w in re.sub(r"[^\w\s]", "", theme.lower()).split() if len(w) > 4]
    seen_ids: set[int] = set()
    results: list[dict] = []

    for word in words[:6]:
        hits = await search_wiki_articles(word, limit=4)
        for h in hits:
            if h["id"] not in seen_ids:
                seen_ids.add(h["id"])
                results.append(h)

    # Riordina per rilevanza: conta quante parole del tema appaiono nel testo
    theme_words = set(theme.lower().split())

    def relevance_score(a: dict) -> int:
        text = (a.get("title", "") + " " + a.get("content_en", "") + " " + a.get("tags", "")).lower()
        return sum(1 for w in theme_words if w in text)

    results.sort(key=relevance_score, reverse=True)
    return results[:limit]


def format_wiki_context(articles: list[dict]) -> str:
    """
    Formatta gli articoli esistenti come contesto per i ricercatori.
    Il formato è pensato per essere leggibile dall'LLM e ispirare il tipo di
    contributo giusto (espansione o nuova voce).
    """
    if not articles:
        return (
            "=== ENCICLOPEDIA DI ACADEMIA INTERMUNDIA ===\n"
            "Nessun articolo esistente su questo tema. Sei il primo a documentarlo.\n"
            "ACTION: CREATE | Title: [titolo descrittivo]\n"
            "=== FINE CONTESTO ENCICLOPEDIA ==="
        )

    lines = [
        "=== ENCICLOPEDIA DI ACADEMIA INTERMUNDIA — ARTICOLI ESISTENTI ===",
        "Leggi con attenzione prima di scrivere. Non duplicare — espandi o crea voce nuova.",
        "",
    ]
    for a in articles:
        rev = a.get("revision_count", 1)
        tags = a.get("tags", "") or "—"
        dept = a.get("department", "") or "—"
        preview = (a.get("content_en") or "")[:500]
        if len(a.get("content_en") or "") > 500:
            preview += "…"
        lines.append(
            f"[ID:{a['id']} | \"{a['title']}\" | dept:{dept} | tags:{tags} | revisioni:{rev}]\n{preview}"
        )
        lines.append("")

    lines.append("=== FINE CONTESTO ENCICLOPEDIA ===")
    return "\n".join(lines)


# ── Action parser ──────────────────────────────────────────────────────────────

def parse_wiki_action(content: str) -> tuple[str, str, str]:
    """
    Analizza l'output del ricercatore per l'istruzione wiki.
    Il ricercatore DEVE iniziare la risposta con:
      ACTION: CREATE | Title: [titolo]
    oppure:
      ACTION: EXPAND | Article: [ID o titolo esatto]

    Ritorna: (action, article_ref, clean_content)
      action       = "CREATE" | "EXPAND"
      article_ref  = nuovo titolo (CREATE) o ID/titolo articolo esistente (EXPAND)
      clean_content = contenuto senza la riga ACTION
    """
    lines = content.strip().split("\n")
    action = "CREATE"
    article_ref = ""
    content_start = 0

    for i, line in enumerate(lines[:4]):
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("ACTION:"):
            parts = stripped.split("|")
            action_word = parts[0].replace("ACTION:", "").replace("action:", "").strip().upper()
            if "EXPAND" in action_word:
                action = "EXPAND"

            for part in parts[1:]:
                if ":" in part:
                    key, _, val = part.partition(":")
                    k = key.strip().upper()
                    if k in ("ARTICLE", "TITLE", "ID", "ARTICOLO", "TITOLO"):
                        article_ref = val.strip()
                        break

            content_start = i + 1
            break

    clean = "\n".join(lines[content_start:]).strip()
    return action, article_ref, clean


# ── Post-research article write ────────────────────────────────────────────────

async def write_wiki_contribution(
    author_id: str,
    round_id: int,
    theme: str,
    action: str,
    article_ref: str,
    content: str,
    department: str = "",
) -> tuple[int, str]:
    """
    Esegui l'azione wiki del ricercatore: CREATE o EXPAND.
    Ritorna (article_id, "created"|"expanded").

    Filosofia Enciclopedia:
    - EXPAND: trova l'articolo (per ID o titolo), aggiunge il nuovo contributo
      come nuova sezione in fondo (non sovrascrive — il vecchio contenuto è preservato)
    - CREATE: crea una nuova voce permanente nell'Enciclopedia
    """
    # Genera tag dal tema
    tags = " ".join(w for w in theme.lower().split() if len(w) > 4)[:200]

    if action == "EXPAND" and article_ref:
        # Cerca per ID numerico
        existing = None
        try:
            art_id = int(article_ref)
            existing = await get_wiki_article(art_id)
        except (ValueError, TypeError):
            pass

        # Cerca per titolo se non trovato per ID
        if not existing:
            hits = await search_wiki_articles(article_ref, limit=3)
            if hits:
                # Prendi quello col titolo più vicino
                ref_lower = article_ref.lower()
                for h in hits:
                    if ref_lower in h["title"].lower() or h["title"].lower() in ref_lower:
                        existing = h
                        break
                if not existing:
                    existing = hits[0]

        if existing:
            # Espansione: appendi nuova sezione al contenuto esistente
            merged = (
                existing.get("content_en") or ""
            ) + f"\n\n---\n\n**Expanded in Round {round_id} by {author_id}:**\n\n{content}"
            summary = f"Round {round_id}: expanded by {author_id}"
            await update_wiki_article(existing["id"], author_id, round_id, merged, summary)
            return existing["id"], "expanded"

    # Fallback su CREATE (anche se l'LLM ha detto EXPAND ma non ha trovato l'articolo)
    title = article_ref if article_ref else f"{theme[:80]}"
    art_id = await create_wiki_article(author_id, round_id, title, content, department=department, tags=tags)
    return art_id, "created"


# ── Senior synthesis article ───────────────────────────────────────────────────

async def write_synthesis_article(
    senior_id: str, round_id: int, theme: str, synthesis_content: str
) -> int:
    """
    Crea o aggiorna l'articolo di sintesi del round.
    I Seniores producono la visione d'insieme: questo diventa una voce Enciclopedia di alto livello.
    """
    synthesis_title = f"Synthesis: {theme[:80]}"
    # Cerca se esiste già una sintesi su questo tema
    hits = await search_wiki_articles(f"Synthesis {theme[:40]}", limit=3)
    existing = next((h for h in hits if "Synthesis" in h.get("title", "")), None)

    if existing:
        merged = (
            existing.get("content_en") or ""
        ) + f"\n\n---\n\n**Senior Synthesis — Round {round_id}:**\n\n{synthesis_content}"
        await update_wiki_article(
            existing["id"], senior_id, round_id, merged,
            f"Round {round_id}: senior synthesis updated"
        )
        return existing["id"]
    else:
        return await create_wiki_article(
            senior_id, round_id, synthesis_title, synthesis_content,
            department="senior-council", tags=f"synthesis round-{round_id}"
        )


# ── Build round summary (per senior review — usa ancora wiki_pages legacy) ────

async def build_round_summary(round_id: int) -> str:
    """Riassunto testuale delle voci enciclopedia di un round per la senior review."""
    pages = await get_wiki_pages(round_id)
    if not pages:
        return "No encyclopedia entries produced in this round."
    parts = []
    for page in pages:
        author = await get_agent(page["author_id"])
        author_name = author["name"] if author else page["author_id"]
        preview = (page.get("content_en") or "")[:500]
        if len(page.get("content_en") or "") > 500:
            preview += "…"
        parts.append(
            f"## {page['title']} (by {author_name})\n"
            f"Status: {page.get('status', 'draft')}\n{preview}\n"
        )
    return "\n\n".join(parts)


# ── Legacy functions (backward compat con wiki_pages) ─────────────────────────

async def get_wiki_pages_by_round(round_id: int) -> list[dict]:
    pages = await get_wiki_pages(round_id)
    result = []
    for page in pages:
        author = await get_agent(page["author_id"])
        enriched = dict(page)
        enriched["author_name"] = author["name"] if author else page["author_id"]
        result.append(enriched)
    return result


async def search_wiki(query: str) -> list[dict]:
    """Cerca su articoli permanenti E wiki_pages legacy."""
    like = f"%{query}%"
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM wiki_pages WHERE title LIKE ? OR content_en LIKE ? ORDER BY id DESC LIMIT 30",
            (like, like),
        ) as cursor:
            rows = await cursor.fetchall()
            legacy = [dict(r) for r in rows]
    articles = await search_wiki_articles(query, limit=20)
    for a in articles:
        a["_type"] = "article"
    for p in legacy:
        p["_type"] = "page"
    return articles + legacy


def format_wikibooks_page(page: dict) -> str:
    title = page.get("title", "Untitled")
    content = page.get("content_en", "")
    author_id = page.get("author_id", "")
    status = page.get("status", "draft")
    created = page.get("created_at", "")
    if "<" not in content:
        paragraphs = "".join(
            f"<p>{para.strip()}</p>" for para in content.split("\n\n") if para.strip()
        )
        content_html = paragraphs or f"<p>{content}</p>"
    else:
        content_html = content
    return (
        f'<article class="wiki-page" id="page-{page.get("id", "")}">' +
        f'  <header><h2>{title}</h2>' +
        f'  <div class="meta">Author: {author_id} | Status: {status} | {created}</div></header>' +
        f'  <div class="wiki-content">{content_html}</div></article>'
    )
