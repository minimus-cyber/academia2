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
