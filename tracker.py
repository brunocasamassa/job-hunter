# tracker.py
# Salva vagas no banco SQLite para evitar alertas duplicados

import sqlite3
from datetime import datetime


DB_PATH = "jobs.db"


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
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
    conn.commit()
    return conn


def is_new(conn: sqlite3.Connection, url: str) -> bool:
    """Retorna True se a vaga ainda não está no banco."""
    row = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone()
    return row is None


def save_job(conn: sqlite3.Connection, job: dict) -> None:
    conn.execute("""
        INSERT OR IGNORE INTO jobs
            (url, title, company, location, source, date_posted, salary, found_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job["job_url"],
        job["title"],
        job["company"],
        job["location"],
        job["source"],
        job["date_posted"],
        job["salary"],
        datetime.now().isoformat(),
    ))
    conn.commit()


def mark_notified(conn: sqlite3.Connection, url: str) -> None:
    conn.execute("UPDATE jobs SET notified = 1 WHERE url = ?", (url,))
    conn.commit()


def purge_old_jobs(conn: sqlite3.Connection, days: int = 10) -> int:
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
    cols = ["url", "title", "company", "location", "source", "date_posted", "salary", "notified", "found_at"]
    return [dict(zip(cols, row)) for row in rows]
