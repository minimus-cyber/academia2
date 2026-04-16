from db import get_db, get_wiki_pages, get_all_wiki_pages, get_wiki_page, get_agent


async def get_wiki_pages_by_round(round_id: int) -> list[dict]:
    """Returns wiki pages for a round with author names joined."""
    pages = await get_wiki_pages(round_id)
    result = []
    for page in pages:
        author = await get_agent(page["author_id"])
        enriched = dict(page)
        enriched["author_name"] = author["name"] if author else page["author_id"]
        result.append(enriched)
    return result


async def search_wiki(query: str) -> list[dict]:
    """Simple full-text search across title and content_en using SQL LIKE."""
    like_query = f"%{query}%"
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM wiki_pages
               WHERE title LIKE ? OR content_en LIKE ?
               ORDER BY id DESC
               LIMIT 50""",
            (like_query, like_query),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


def format_wikibooks_page(page: dict) -> str:
    """Returns an HTML fragment for a single wiki page."""
    title = page.get("title", "Untitled")
    content = page.get("content_en", "")
    author_id = page.get("author_id", "")
    status = page.get("status", "draft")
    created = page.get("created_at", "")

    # Wrap plain text in paragraphs if no HTML tags found
    if "<" not in content:
        paragraphs = "".join(f"<p>{para.strip()}</p>" for para in content.split("\n\n") if para.strip())
        content_html = paragraphs or f"<p>{content}</p>"
    else:
        content_html = content

    return (
        f'<article class="wiki-page" id="page-{page.get("id", "")}">'
        f'  <header>'
        f'    <h2>{title}</h2>'
        f'    <div class="meta">Author: {author_id} | Status: {status} | {created}</div>'
        f'  </header>'
        f'  <div class="wiki-content">{content_html}</div>'
        f'</article>'
    )


async def build_round_summary(round_id: int) -> str:
    """
    Builds a concise text summary of all wiki pages in a round
    for use as senior review context.
    """
    pages = await get_wiki_pages(round_id)
    if not pages:
        return "No wiki pages produced in this round."

    parts = []
    for page in pages:
        author = await get_agent(page["author_id"])
        author_name = author["name"] if author else page["author_id"]
        content_preview = (page.get("content_en") or "")[:500]
        if len(page.get("content_en") or "") > 500:
            content_preview += "..."
        parts.append(
            f"## {page['title']} (by {author_name})\n"
            f"Status: {page.get('status', 'draft')}\n"
            f"{content_preview}\n"
        )
    return "\n\n".join(parts)
