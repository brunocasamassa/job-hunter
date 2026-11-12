# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run once immediately
python main.py

# Run on a schedule (every INTERVALO_MINUTOS — currently 720 = 12h — keeps terminal open)
python scheduler.py

# Run in background (Linux/Mac)
nohup python scheduler.py > log.txt 2>&1 &

# Tests (no network: JobSpy, LinkedIn and Telegram are mocked)
pip install -r requirements-dev.txt
pytest
```

## Architecture

The pipeline is linear: **scrape → keep new → enrich → save → notify pending → mark delivered**.

```
scheduler.py  →  main.py  →  job_scraper.py   (JobSpy: LinkedIn, Indeed, Glassdoor)
                          →  tracker.py        (SQLite jobs.db — dedup by URL, pending queue)
                          →  notifier.py       (Telegram Bot API)
```

**`main.py`** is the entry point. It calls `fetch_jobs()`, keeps jobs whose URL is not in the DB, calls `enrich_linkedin_details()` on those new jobs, saves them (`notified = 0`), then sends **all pending jobs** (`get_pending_jobs()`: new ones plus earlier failed deliveries). Only URLs returned by `notify_jobs()` are marked as notified. `HISTORY_DAYS` (180) controls how long seen jobs are remembered; `HOURS_OLD` (24) is the search window.

**`job_scraper.py`** searches `SEARCH_TERM` ("Android") in every `REGIONS` entry on LinkedIn + Indeed, and in every `GLASSDOOR_REGIONS` entry on Glassdoor. `REGIONS` is a list of `(location, country_indeed)` tuples — `location` is used by LinkedIn/Glassdoor, `country_indeed` restricts Indeed's regional domain. `is_relevant()` filters titles case-insensitively: `KEYWORDS` match as substrings, `BLACKLIST_TITLES` match as whole words. Results are deduplicated by `job_url`. `enrich_linkedin_details()` fetches description + `url_direct` (company application link) for LinkedIn jobs via JobSpy's internal `LinkedIn._get_job_details` (JobSpy 1.1.82), with a per-run cap and an early stop after consecutive failures.

**`tracker.py`** uses SQLite (`jobs.db`) with `url` as primary key and `sqlite3.Row` rows. `init_db()` adds columns introduced later (`url_direct`, `description`) to existing databases. Key functions: `is_new()`, `save_job()`, `get_pending_jobs()` (returns dicts with a `job_url` key, same shape as the scraper), `mark_notified()`, `purge_old_jobs()`, `get_all_jobs()`.

**`notifier.py`** sends messages via Telegram Bot API (`parse_mode=HTML`; every dynamic field goes through `_esc()`). Credentials come from `.env` (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, loaded with python-dotenv). `send_telegram()` waits `retry_after` on HTTP 429 and redacts the token from error output. `notify_jobs()` returns the set of delivered job URLs.

**`jobspy_patches.py`** and **`logger.py`** monkeypatch JobSpy/requests/tls_client at import time (Glassdoor bug workarounds and verbose Glassdoor logging).

## Key configuration points

| What | Where |
|---|---|
| Search term | `SEARCH_TERM` in `job_scraper.py` |
| Title keywords | `KEYWORDS` in `job_scraper.py` |
| Title blacklist | `BLACKLIST_TITLES` in `job_scraper.py` |
| Countries/regions | `REGIONS` / `GLASSDOOR_REGIONS` in `job_scraper.py` |
| LinkedIn detail fetching | `LINKEDIN_FETCH_DETAILS`, `LINKEDIN_DETAILS_*` in `job_scraper.py` |
| Schedule interval | `INTERVALO_MINUTOS` in `scheduler.py` |
| Search window (hours) | `HOURS_OLD` in `main.py` |
| History retention (days) | `HISTORY_DAYS` in `main.py` |
| Telegram credentials | `.env` → `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` |
