# tracker.py
# Salva vagas no banco SQLite para evitar alertas duplicados

import sqlite3
from datetime import datetime


DB_PATH = "jobs.db"

# Colunas criadas depois da primeira versão. init_db() as adiciona em bancos
# antigos, sem perder o que já está salvo.
_ADDED_COLUMNS = {
    "url_direct":  "TEXT",
    "description": "TEXT",
}


def init_db(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            url         TEXT PRIMARY KEY,
            title       TEXT,
            company     TEXT,
            location    TEXT,
            source      TEXT,
            date_posted TEXT,
            salary      TEXT,
            notified    INTEGER DEFAULT 0,
            found_at    TEXT
        )
    """)
    _add_missing_columns(conn)
    conn.commit()
    return conn


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    for column, sql_type in _ADDED_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {sql_type}")


def is_new(conn: sqlite3.Connection, url: str) -> bool:
    """Retorna True se a vaga ainda não está no banco."""
    row = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone()
    return row is None


def save_job(conn: sqlite3.Connection, job: dict) -> None:
    conn.execute("""
        INSERT OR IGNORE INTO jobs
            (url, title, company, location, source, date_posted, salary,
             url_direct, description, found_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job["job_url"],
        job["title"],
        job["company"],
        job["location"],
        job["source"],
        job["date_posted"],
        job["salary"],
        job.get("url_direct", ""),
        job.get("description", ""),
        datetime.now().isoformat(),
    ))
    conn.commit()


def get_pending_jobs(conn: sqlite3.Connection) -> list[dict]:
    """
    Vagas salvas que ainda não chegaram no Telegram: as novas desta execução e
    as que falharam no envio de execuções anteriores. Mesmo formato de dict
    que o scraper produz (chave `job_url`), para o notifier tratar igual.
    """
    rows = conn.execute("""
        SELECT url AS job_url, title, company, location, source,
               date_posted, salary, url_direct
        FROM jobs
        WHERE notified = 0
        ORDER BY found_at
    """).fetchall()
    return [dict(row) for row in rows]


def mark_notified(conn: sqlite3.Connection, url: str) -> None:
    conn.execute("UPDATE jobs SET notified = 1 WHERE url = ?", (url,))
    conn.commit()


def purge_old_jobs(conn: sqlite3.Connection, days: int = 180) -> int:
    """Remove vagas com mais de `days` dias. Retorna quantas foram deletadas."""
    conn.execute(
        "DELETE FROM jobs WHERE found_at < datetime('now', ?)",
        (f"-{days} days",)
    )
    deleted = conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()
    return deleted


def get_all_jobs(conn: sqlite3.Connection) -> list[dict]:
    """Retorna todas as vagas salvas (para debug/consulta)."""
    rows = conn.execute("SELECT * FROM jobs ORDER BY found_at DESC").fetchall()
    return [dict(row) for row in rows]
