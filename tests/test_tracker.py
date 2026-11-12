import sqlite3

import tracker


def _job(url="https://example.com/jobs/1", **overrides):
    job = {
        "job_url": url,
        "title": "Senior Android Engineer",
        "company": "ACME",
        "location": "Munich, BY, DE",
        "source": "linkedin",
        "date_posted": "2026-11-06",
        "salary": "",
        "url_direct": "https://careers.acme.com/apply/1",
        "description": "Kotlin, AOSP",
    }
    job.update(overrides)
    return job


def test_saved_job_is_pending_until_notified(tmp_path):
    conn = tracker.init_db(str(tmp_path / "jobs.db"))
    tracker.save_job(conn, _job())

    pending = tracker.get_pending_jobs(conn)
    assert [j["job_url"] for j in pending] == ["https://example.com/jobs/1"]
    assert pending[0]["url_direct"] == "https://careers.acme.com/apply/1"

    tracker.mark_notified(conn, "https://example.com/jobs/1")
    assert tracker.get_pending_jobs(conn) == []
    assert not tracker.is_new(conn, "https://example.com/jobs/1")


def test_init_db_migrates_old_schema_without_losing_rows(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.execute("""
        CREATE TABLE jobs (
            url TEXT PRIMARY KEY, title TEXT, company TEXT, location TEXT,
            source TEXT, date_posted TEXT, salary TEXT,
            notified INTEGER DEFAULT 0, found_at TEXT
        )
    """)
    old.execute(
        "INSERT INTO jobs (url, title, notified, found_at) VALUES (?, ?, 1, ?)",
        ("https://example.com/old", "Android Dev", "2026-11-01T10:00:00"),
    )
    old.commit()
    old.close()

    conn = tracker.init_db(path)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    assert {
        "url_direct", "description", "fingerprint", "country", "eligibility",
        "eligibility_reason", "languages", "score", "repost_of", "suppressed",
    } <= columns
    assert not tracker.is_new(conn, "https://example.com/old")
    assert tracker.get_pending_jobs(conn) == []  # já notificada antes da migração


def test_suppressed_job_is_kept_but_not_pending(tmp_path):
    conn = tracker.init_db(str(tmp_path / "jobs.db"))
    tracker.save_job(conn, _job(eligibility="ineligible"), suppressed="ineligible")

    assert tracker.get_pending_jobs(conn) == []
    saved = tracker.get_all_jobs(conn)[0]
    assert saved["suppressed"] == "ineligible"
    assert saved["notified"] == 1


def test_first_seen_by_fingerprint(tmp_path):
    conn = tracker.init_db(str(tmp_path / "jobs.db"))
    assert tracker.first_seen(conn, "acme|android|germany") is None

    tracker.save_job(conn, _job("https://example.com/a", fingerprint="acme|android|germany"))
    tracker.save_job(conn, _job("https://example.com/b", fingerprint="acme|android|germany"))

    first = tracker.first_seen(conn, "acme|android|germany")
    assert first == min(row["found_at"] for row in tracker.get_all_jobs(conn))


def test_pending_jobs_come_by_score(tmp_path):
    conn = tracker.init_db(str(tmp_path / "jobs.db"))
    tracker.save_job(conn, _job("https://example.com/low", score=3))
    tracker.save_job(conn, _job("https://example.com/high", score=9))
    tracker.save_job(conn, _job("https://example.com/legacy"))  # sem nota (linha antiga)

    assert [j["job_url"] for j in tracker.get_pending_jobs(conn)] == [
        "https://example.com/high",
        "https://example.com/low",
        "https://example.com/legacy",
    ]


def test_purge_keeps_recent_jobs(tmp_path):
    conn = tracker.init_db(str(tmp_path / "jobs.db"))
    tracker.save_job(conn, _job())
    assert tracker.purge_old_jobs(conn, days=180) == 0
    assert len(tracker.get_all_jobs(conn)) == 1
