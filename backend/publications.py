import os
from datetime import datetime
from db import get_publication, get_all_publications

PUBLICATIONS_DIR = "/root/academia2/publications"


def build_wikibooks_html(
    title: str,
    sections: list[dict],
    authors: list[str],
    round_id: int,
) -> str:
    """
    Builds a complete Wikibooks-style HTML5 document.
    sections: list of {"heading": str, "content": str}
    authors: list of author name strings
    Returns complete HTML string with Weinrot palette.
    """
    now = datetime.utcnow().strftime("%Y-%m-%d")
    authors_str = ", ".join(authors) if authors else "Academia Intermundia DAOs"

    # Build TOC
    toc_items = ""
    for i, section in enumerate(sections, 1):
        heading = section.get("heading", f"Section {i}")
        anchor = f"section-{i}"
        toc_items += f'    <li><a href="#{anchor}">{heading}</a></li>\n'

    # Build section HTML
    sections_html = ""
    for i, section in enumerate(sections, 1):
        heading = section.get("heading", f"Section {i}")
        content = section.get("content", "")
        anchor = f"section-{i}"

        # If content has no HTML tags, wrap in paragraphs
        if "<" not in content:
            paragraphs = "".join(
                f"    <p>{para.strip()}</p>\n"
                for para in content.split("\n\n")
                if para.strip()
            )
            content_html = paragraphs or f"    <p>{content}</p>\n"
        else:
            content_html = content

        sections_html += (
            f'  <section id="{anchor}">\n'
            f'    <h2>{heading}</h2>\n'
            f'{content_html}'
            f'  </section>\n\n'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>
    /* ── Academia Intermundia — Weinrot Design System ── */
    :root {{
      --weinrot: #9B1B30;
      --weinrot-dark: #6d1322;
      --weinrot-light: #c4233e;
      --bg: #ffffff;
      --text: #1a1a1a;
      --muted: #555;
      --border: #e0e0e0;
      --code-bg: #f5f5f5;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: 'Georgia', 'Times New Roman', serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.75;
      padding: 0;
    }}

    header.pub-header {{
      background: var(--weinrot);
      color: #fff;
      padding: 3rem 2rem 2rem;
      text-align: center;
    }}

    header.pub-header h1 {{
      font-size: 2rem;
      font-weight: 700;
      margin-bottom: 0.5rem;
      letter-spacing: 0.02em;
    }}

    header.pub-header .meta {{
      font-size: 0.9rem;
      opacity: 0.85;
      font-family: 'Droid Sans Mono', 'Courier New', monospace;
    }}

    nav.toc {{
      background: #fafafa;
      border-left: 4px solid var(--weinrot);
      margin: 2rem auto;
      max-width: 800px;
      padding: 1.5rem 2rem;
    }}

    nav.toc h2 {{
      font-size: 1rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--weinrot);
      margin-bottom: 1rem;
      font-family: 'Droid Sans Mono', 'Courier New', monospace;
    }}

    nav.toc ol {{
      padding-left: 1.5rem;
    }}

    nav.toc li {{
      margin-bottom: 0.4rem;
    }}

    nav.toc a {{
      color: var(--weinrot);
      text-decoration: none;
    }}

    nav.toc a:hover {{
      text-decoration: underline;
    }}

    main {{
      max-width: 800px;
      margin: 0 auto;
      padding: 1rem 2rem 4rem;
    }}

    section {{
      margin-bottom: 3rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 2rem;
    }}

    section:last-child {{
      border-bottom: none;
    }}

    h2 {{
      color: var(--weinrot);
      font-size: 1.4rem;
      margin-bottom: 1rem;
      padding-bottom: 0.3rem;
      border-bottom: 2px solid var(--weinrot);
    }}

    h3 {{
      color: var(--weinrot-dark);
      font-size: 1.1rem;
      margin: 1.5rem 0 0.5rem;
    }}

    p {{
      margin-bottom: 1rem;
    }}

    ul, ol {{
      margin: 0.5rem 0 1rem 1.5rem;
    }}

    li {{
      margin-bottom: 0.3rem;
    }}

    blockquote {{
      border-left: 3px solid var(--weinrot);
      padding-left: 1rem;
      margin: 1rem 0;
      color: var(--muted);
      font-style: italic;
    }}

    code, pre {{
      font-family: 'Droid Sans Mono', 'Courier New', monospace;
      background: var(--code-bg);
      font-size: 0.88rem;
    }}

    pre {{
      padding: 1rem;
      overflow-x: auto;
      border-left: 3px solid var(--weinrot);
      margin: 1rem 0;
    }}

    code {{
      padding: 0.1em 0.3em;
      border-radius: 2px;
    }}

    footer.pub-footer {{
      background: var(--weinrot);
      color: #fff;
      text-align: center;
      padding: 2rem;
      font-family: 'Droid Sans Mono', 'Courier New', monospace;
      font-size: 0.85rem;
    }}

    footer.pub-footer a {{
      color: #ffccd4;
    }}

    .badge {{
      display: inline-block;
      background: var(--weinrot-light);
      color: #fff;
      font-size: 0.75rem;
      padding: 0.15rem 0.5rem;
      border-radius: 2px;
      font-family: 'Droid Sans Mono', 'Courier New', monospace;
      margin-left: 0.5rem;
      vertical-align: middle;
    }}
  </style>
</head>
<body>

  <header class="pub-header">
    <h1>{title}</h1>
    <div class="meta">
      Academia Intermundia v2.0 &nbsp;|&nbsp;
      Round {round_id} &nbsp;|&nbsp;
      Published {now} &nbsp;|&nbsp;
      Authors: {authors_str}
    </div>
  </header>

  <nav class="toc">
    <h2>Table of Contents</h2>
    <ol>
{toc_items}    </ol>
  </nav>

  <main>
{sections_html}  </main>

  <footer class="pub-footer">
    <p>
      <strong>Academia Intermundia</strong> &mdash; Version 2.0<br/>
      Founded by Professor Francesco Verderosa &nbsp;&bull;&nbsp;
      DAOs operate under empiricism, immanentism, and advancement<br/>
      Published {now} &nbsp;&bull;&nbsp;
      <a href="https://wikibooks.org" target="_blank">Wikibooks Format</a>
    </p>
  </footer>

</body>
</html>"""

    return html


async def save_publication_file(pub_id: int, html_content: str):
    """Saves HTML to /root/academia2/publications/pub_{pub_id}.html"""
    os.makedirs(PUBLICATIONS_DIR, exist_ok=True)
    path = os.path.join(PUBLICATIONS_DIR, f"pub_{pub_id}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)


async def get_publication_detail(pub_id: int) -> dict | None:
    return await get_publication(pub_id)


async def list_publications_all() -> list[dict]:
    return await get_all_publications()
