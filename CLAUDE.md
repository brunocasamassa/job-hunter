# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run once immediately
python main.py

# Run on a schedule (every 10 minutes, keeps terminal open)
python scheduler.py

# Run in background (Linux/Mac)
nohup python scheduler.py > log.txt 2>&1 &
```

## Architecture

The pipeline is linear: **scrape → deduplicate → notify**.

```
scheduler.py  →  main.py  →  job_scraper.py   (JobSpy: LinkedIn, Indeed, Glassdoor)
                          →  tracker.py        (SQLite jobs.db — dedup by URL)
                          →  notifier.py       (Telegram Bot API)
```

**`main.py`** is the entry point. It calls `fetch_jobs()`, filters out already-seen URLs via `tracker.py`, sends new ones to Telegram via `notifier.py`, then marks them as notified.

**`job_scraper.py`** iterates over `KEYWORDS × REGIONS` (3 keywords × 23 countries = 69 requests per run). `REGIONS` is a list of `(location, country_indeed)` tuples — `location` is used by LinkedIn/Glassdoor, `country_indeed` restricts Indeed's regional domain. Results are deduplicated by `job_url` before returning.

**`tracker.py`** uses SQLite (`jobs.db`) with `job_url` as primary key. Key functions: `is_new()`, `save_job()`, `mark_notified()`, `get_all_jobs()` (for manual inspection).

**`notifier.py`** sends messages via Telegram Bot API. Credentials (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`) are hardcoded at the top of the file — fill these in before running.

> **Note:** `main.py` imports from `scrapers.job_scraper` but the file currently lives at the project root as `job_scraper.py`. If this import fails, either move the file to a `scrapers/` subdirectory with an `__init__.py`, or fix the import to `from job_scraper import fetch_jobs`.

## Key configuration points

| What | Where |
|---|---|
| Search keywords | `KEYWORDS` in `job_scraper.py` |
| Title blacklist | `BLACKLIST_TITLES` in `job_scraper.py` |
| Countries/regions | `REGIONS` in `job_scraper.py` |
| Schedule interval | `INTERVALO_MINUTOS` in `scheduler.py` |
| How many hours back to search | `hours_old` in `main.py` → `fetch_jobs(hours_old=24)` |
| Telegram credentials | `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` in `notifier.py` |
