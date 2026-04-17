import aiosqlite
from contextlib import asynccontextmanager
from datetime import datetime
from config import DB_PATH


@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db():
    async with get_db() as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT,
                role TEXT,
                department TEXT,
                discipline TEXT,
                symbol TEXT,
                origin TEXT,
                identity_prompt TEXT,
                model_id TEXT,
                active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                theme_en TEXT,
                theme_it TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now')),
                ratified_at TEXT
            );

            CREATE TABLE IF NOT EXISTS wiki_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER,
                author_id TEXT,
                title TEXT,
                content_en TEXT,
                status TEXT DEFAULT 'draft',
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (round_id) REFERENCES rounds(id),
                FOREIGN KEY (author_id) REFERENCES agents(id)
            );

            CREATE TABLE IF NOT EXISTS publications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER,
                title TEXT,
                content_en_html TEXT,
                content_it_html TEXT,
                format TEXT DEFAULT 'wikibooks',
                status TEXT DEFAULT 'draft',
                published_at TEXT,
                FOREIGN KEY (round_id) REFERENCES rounds(id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER,
                agent_id TEXT,
                content TEXT,
                msg_type TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (round_id) REFERENCES rounds(id),
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            );

            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT,
                content TEXT,
                round_id INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS lab_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER,
                author_id TEXT,
                filename TEXT,
                html_content TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS student_theses (
                student_id TEXT PRIMARY KEY,
                title TEXT,
                abstract TEXT,
                status TEXT DEFAULT 'assigned',
                assigned_round_id INTEGER
            );

            -- ── WIKI REALE ────────────────────────────────────────────────
            -- Articoli permanenti, indipendenti dai round (filosofia Wikipedia)
            CREATE TABLE IF NOT EXISTS wiki_articles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                slug        TEXT UNIQUE NOT NULL,
                title       TEXT NOT NULL,
                content_en  TEXT DEFAULT '',
                content_it  TEXT DEFAULT '',
                department  TEXT DEFAULT '',
                tags        TEXT DEFAULT '',
                status      TEXT DEFAULT 'draft',
                created_by  TEXT,
                last_round_id INTEGER,
                revision_count INTEGER DEFAULT 1,
                created_at  TEXT,
                updated_at  TEXT,
                FOREIGN KEY (created_by) REFERENCES agents(id)
            );

            -- Ogni edit è una revisione tracciata (nulla si perde)
            CREATE TABLE IF NOT EXISTS wiki_article_revisions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id  INTEGER NOT NULL,
                content_en  TEXT NOT NULL,
                author_id   TEXT NOT NULL,
                round_id    INTEGER,
                edit_summary TEXT DEFAULT '',
                created_at  TEXT NOT NULL,
                FOREIGN KEY (article_id) REFERENCES wiki_articles(id),
                FOREIGN KEY (author_id)  REFERENCES agents(id)
            );

            -- Cross-link tra articoli (la conoscenza è una rete)
            CREATE TABLE IF NOT EXISTS wiki_article_links (
                from_article_id INTEGER NOT NULL,
                to_article_id   INTEGER NOT NULL,
                PRIMARY KEY (from_article_id, to_article_id),
                FOREIGN KEY (from_article_id) REFERENCES wiki_articles(id),
                FOREIGN KEY (to_article_id)   REFERENCES wiki_articles(id)
            );
        """)
        await db.commit()


async def get_agent(agent_id: str) -> dict | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_agents_by_role(role: str) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM agents WHERE role = ? AND active = 1", (role,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_agents_by_department(dept: str) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM agents WHERE department = ? AND active = 1", (dept,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_all_agents() -> list[dict]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM agents ORDER BY role, id") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def create_round(theme_en: str, theme_it: str) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO rounds (theme_en, theme_it, status, created_at) VALUES (?, ?, 'active', datetime('now'))",
            (theme_en, theme_it),
        )
        await db.commit()
        return cursor.lastrowid


async def get_round(round_id: int) -> dict | None:
    async with get_db() as db:
        async with db.execute("SELECT * FROM rounds WHERE id = ?", (round_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_all_rounds() -> list[dict]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM rounds ORDER BY id DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def add_message(round_id: int, agent_id: str, content: str, msg_type: str) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO messages (round_id, agent_id, content, msg_type, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (round_id, agent_id, content, msg_type),
        )
        await db.commit()
        return cursor.lastrowid


async def get_messages(round_id: int) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM messages WHERE round_id = ? ORDER BY id", (round_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def add_wiki_page(round_id: int, author_id: str, title: str, content_en: str) -> int:
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO wiki_pages (round_id, author_id, title, content_en, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'draft', ?, ?)",
            (round_id, author_id, title, content_en, now, now),
        )
        await db.commit()
        return cursor.lastrowid


async def get_wiki_pages(round_id: int) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM wiki_pages WHERE round_id = ? ORDER BY id", (round_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def approve_wiki_page(page_id: int):
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            "UPDATE wiki_pages SET status = 'approved', updated_at = ? WHERE id = ?",
            (now, page_id),
        )
        await db.commit()


async def update_wiki_page_content(page_id: int, content_en: str):
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            "UPDATE wiki_pages SET content_en = ?, status = 'revised', updated_at = ? WHERE id = ?",
            (content_en, now, page_id),
        )
        await db.commit()


async def add_lab_artifact(round_id: int, author_id: str, filename: str, html_content: str) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO lab_artifacts (round_id, author_id, filename, html_content, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (round_id, author_id, filename, html_content),
        )
        await db.commit()
        return cursor.lastrowid


async def add_memory(agent_id: str, content: str, round_id: int = None) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO memories (agent_id, content, round_id, created_at) VALUES (?, ?, ?, datetime('now'))",
            (agent_id, content, round_id),
        )
        await db.commit()
        return cursor.lastrowid


async def get_recent_memories(agent_id: str, limit: int = 5) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM memories WHERE agent_id = ? ORDER BY id DESC LIMIT ?",
            (agent_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def create_publication(round_id: int, title: str, content_en_html: str, format: str = "wikibooks") -> int:
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO publications (round_id, title, content_en_html, format, status) VALUES (?, ?, ?, ?, 'draft')",
            (round_id, title, content_en_html, format),
        )
        await db.commit()
        return cursor.lastrowid


async def update_publication_it(pub_id: int, content_it_html: str):
    async with get_db() as db:
        await db.execute(
            "UPDATE publications SET content_it_html = ? WHERE id = ?",
            (content_it_html, pub_id),
        )
        await db.commit()


async def publish_publication(pub_id: int):
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            "UPDATE publications SET status = 'published', published_at = ? WHERE id = ?",
            (now, pub_id),
        )
        await db.commit()


async def get_publication(pub_id: int) -> dict | None:
    async with get_db() as db:
        async with db.execute("SELECT * FROM publications WHERE id = ?", (pub_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_all_publications() -> list[dict]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM publications ORDER BY id DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_all_wiki_pages() -> list[dict]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM wiki_pages ORDER BY id DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_wiki_page(page_id: int) -> dict | None:
    async with get_db() as db:
        async with db.execute("SELECT * FROM wiki_pages WHERE id = ?", (page_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_lab_artifacts(round_id: int) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM lab_artifacts WHERE round_id = ? ORDER BY id", (round_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def set_round_status(round_id: int, status: str):
    async with get_db() as db:
        await db.execute("UPDATE rounds SET status = ? WHERE id = ?", (status, round_id))
        await db.commit()


async def ratify_round(round_id: int):
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            "UPDATE rounds SET status = 'ratified', ratified_at = ? WHERE id = ?",
            (now, round_id),
        )
        await db.commit()


async def close_round(round_id: int):
    async with get_db() as db:
        await db.execute("UPDATE rounds SET status = 'closed' WHERE id = ?", (round_id,))
        await db.commit()


async def count_agents() -> int:
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) FROM agents") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def upsert_student_thesis(student_id: str, title: str, abstract: str, round_id: int):
    async with get_db() as db:
        await db.execute(
            """INSERT INTO student_theses (student_id, title, abstract, status, assigned_round_id)
               VALUES (?, ?, ?, 'assigned', ?)
               ON CONFLICT(student_id) DO UPDATE SET
                   title = excluded.title,
                   abstract = excluded.abstract,
                   assigned_round_id = excluded.assigned_round_id""",
            (student_id, title, abstract, round_id),
        )
        await db.commit()


async def get_student_thesis(student_id: str) -> dict | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM student_theses WHERE student_id = ?", (student_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


# ── Direct Messages ──────────────────────────────────────────────────────────

async def init_dm_table():
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS direct_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                read_at TEXT
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_dm_from ON direct_messages(from_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_dm_to ON direct_messages(to_id)")
        await db.commit()


async def create_dm(from_id: str, to_id: str, content: str) -> int:
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO direct_messages (from_id, to_id, content) VALUES (?, ?, ?)",
            (from_id, to_id, content),
        )
        await db.commit()
        return cursor.lastrowid


async def get_dm_thread(participant_a: str, participant_b: str, limit: int = 50) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM direct_messages
               WHERE (from_id=? AND to_id=?) OR (from_id=? AND to_id=?)
               ORDER BY id DESC LIMIT ?""",
            (participant_a, participant_b, participant_b, participant_a, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in reversed(rows)]


async def get_dm_conversations(participant: str) -> list[dict]:
    """Return latest message per conversation thread for a participant."""
    async with get_db() as db:
        async with db.execute(
            """SELECT
                 CASE WHEN from_id=? THEN to_id ELSE from_id END AS other,
                 content, created_at, read_at,
                 MAX(id) AS last_id
               FROM direct_messages
               WHERE from_id=? OR to_id=?
               GROUP BY other
               ORDER BY last_id DESC""",
            (participant, participant, participant),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def mark_dm_read(participant: str, other: str):
    async with get_db() as db:
        await db.execute(
            """UPDATE direct_messages SET read_at=datetime('now')
               WHERE to_id=? AND from_id=? AND read_at IS NULL""",
            (participant, other),
        )
        await db.commit()


# ── Wiki Articles (filosofia Wikipedia) ──────────────────────────────────────

import re as _re

def _make_slug(title: str) -> str:
    """Converte titolo in slug URL-safe."""
    s = title.lower().strip()
    s = _re.sub(r"[^\w\s-]", "", s)
    s = _re.sub(r"[\s_]+", "-", s)
    s = _re.sub(r"-{2,}", "-", s).strip("-")
    return s[:100]


async def create_wiki_article(
    author_id: str, round_id: int, title: str, content_en: str,
    department: str = "", tags: str = ""
) -> int:
    """Crea un nuovo articolo wiki permanente. Ritorna l'id articolo."""
    now = datetime.utcnow().isoformat()
    base_slug = _make_slug(title)
    slug = base_slug
    # Risolvi conflitti slug
    async with get_db() as db:
        for i in range(1, 20):
            async with db.execute("SELECT id FROM wiki_articles WHERE slug = ?", (slug,)) as cur:
                row = await cur.fetchone()
            if not row:
                break
            slug = f"{base_slug}-{i}"
        cursor = await db.execute(
            """INSERT INTO wiki_articles
               (slug, title, content_en, department, tags, status, created_by,
                last_round_id, revision_count, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'published', ?, ?, 1, ?, ?)""",
            (slug, title, content_en, department, tags, author_id, round_id, now, now),
        )
        article_id = cursor.lastrowid
        # Prima revisione
        await db.execute(
            """INSERT INTO wiki_article_revisions
               (article_id, content_en, author_id, round_id, edit_summary, created_at)
               VALUES (?, ?, ?, ?, 'Initial version', ?)""",
            (article_id, content_en, author_id, round_id, now),
        )
        await db.commit()
    return article_id


async def update_wiki_article(
    article_id: int, author_id: str, round_id: int,
    content_en: str, edit_summary: str = ""
) -> None:
    """Aggiorna un articolo wiki esistente e salva la revisione precedente."""
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        # Salva revisione
        await db.execute(
            """INSERT INTO wiki_article_revisions
               (article_id, content_en, author_id, round_id, edit_summary, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (article_id, content_en, author_id, round_id, edit_summary, now),
        )
        # Aggiorna articolo corrente
        await db.execute(
            """UPDATE wiki_articles
               SET content_en = ?, last_round_id = ?, updated_at = ?,
                   revision_count = revision_count + 1, status = 'published'
               WHERE id = ?""",
            (content_en, round_id, now, article_id),
        )
        await db.commit()


async def get_wiki_article(article_id: int) -> dict | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM wiki_articles WHERE id = ?", (article_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_wiki_article_by_slug(slug: str) -> dict | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM wiki_articles WHERE slug = ?", (slug,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_all_wiki_articles(limit: int = 200) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM wiki_articles ORDER BY updated_at DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def search_wiki_articles(query: str, limit: int = 10) -> list[dict]:
    """Full-text search su titolo, contenuto e tag degli articoli permanenti."""
    like = f"%{query}%"
    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM wiki_articles
               WHERE title LIKE ? OR content_en LIKE ? OR tags LIKE ?
               ORDER BY updated_at DESC LIMIT ?""",
            (like, like, like, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_wiki_article_revisions(article_id: int) -> list[dict]:
    """Ritorna la cronologia completa delle revisioni di un articolo."""
    async with get_db() as db:
        async with db.execute(
            """SELECT r.*, a.name as author_name
               FROM wiki_article_revisions r
               LEFT JOIN agents a ON r.author_id = a.id
               WHERE r.article_id = ?
               ORDER BY r.id DESC""",
            (article_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def link_wiki_articles(from_id: int, to_id: int) -> None:
    """Crea un cross-link direzionale tra due articoli wiki."""
    async with get_db() as db:
        await db.execute(
            "INSERT OR IGNORE INTO wiki_article_links (from_article_id, to_article_id) VALUES (?, ?)",
            (from_id, to_id),
        )
        await db.commit()


async def get_wiki_article_links(article_id: int) -> list[dict]:
    """Ritorna gli articoli linkati da questo articolo (outbound links)."""
    async with get_db() as db:
        async with db.execute(
            """SELECT a.* FROM wiki_articles a
               JOIN wiki_article_links l ON l.to_article_id = a.id
               WHERE l.from_article_id = ?""",
            (article_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_wiki_articles_by_round(round_id: int) -> list[dict]:
    """Articoli creati o modificati in un dato round."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM wiki_articles WHERE last_round_id = ? ORDER BY updated_at DESC",
            (round_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_all_lab_artifacts() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT la.*, a.name as author_name, a.department "
            "FROM lab_artifacts la "
            "LEFT JOIN agents a ON la.author_id = a.id "
            "ORDER BY la.id DESC"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

async def get_lab_artifact_by_id(artifact_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT la.*, a.name as author_name, a.department "
            "FROM lab_artifacts la "
            "LEFT JOIN agents a ON la.author_id = a.id "
            "WHERE la.id = ?", (artifact_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

