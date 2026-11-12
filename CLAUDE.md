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

Pipeline: **scrape → keep new URLs → dedupe → enrich → classify + score → save → send pending digest → mark delivered**.

```
scheduler.py  →  main.py  →  job_scraper.py   (JobSpy: LinkedIn, Indeed, Glassdoor)
                          →  dedupe.py         (company|title|country fingerprint)
                          →  eligibility.py    (can the user work there? language required?)
                          →  ranking.py        (0–10 score)
                          →  tracker.py        (SQLite jobs.db — history, pending queue)
                          →  notifier.py       (Telegram digest)
```

**`main.py`** is the entry point. `run()` fetches jobs, keeps those whose URL is not in the DB and hands them to `process_new_jobs()`, which: fingerprints them (`dedupe.fingerprint`), drops same-run duplicates (`split_duplicates`, keeps the most complete version), suppresses jobs whose fingerprint was first seen less than `REPOST_WINDOW_DAYS` (30) ago and tags older ones with `repost_of`, calls `enrich_linkedin_details()` only on the remaining candidates (visa countries first, since description decides their eligibility), then classifies and scores each one. Ineligible jobs are saved with `suppressed="ineligible"` (not sent) unless `SHOW_INELIGIBLE`; duplicates are saved with `suppressed="duplicate"`. Afterwards **all pending jobs** (`notified = 0`: new ones plus earlier failed deliveries) go to `notify_jobs()`, and only the URLs it returns are marked as notified. `HISTORY_DAYS` (180) controls retention; `HOURS_OLD` (24) is the search window.

**`job_scraper.py`** runs every term in `SEARCH_TERMS` against every `REGIONS` entry on LinkedIn + Indeed and every `GLASSDOOR_REGIONS` entry on Glassdoor. Region entries are `(location, country_indeed, mode)`: `location` is used by LinkedIn/Glassdoor, `country_indeed` picks Indeed's domain and becomes the job's `country`, and `mode` is `ALL` or `REMOTE` (remote-only search, passed as `is_remote` to JobSpy via `logger.debug_scrape`). `is_relevant()` filters titles case-insensitively: `KEYWORDS` match as substrings, `BLACKLIST_TITLES` as whole words. `enrich_linkedin_details()` fetches description + `url_direct` for LinkedIn jobs via JobSpy's internal `LinkedIn._get_job_details` (JobSpy 1.1.82), with a per-run cap and an early stop after consecutive failures.

**`eligibility.py`** — `classify(job)` returns `Eligibility(status, reason, languages)` with status `ELIGIBLE` / `MAYBE` / `INELIGIBLE`. Order: EU/EEA/Switzerland (`FREE_MOVEMENT_COUNTRIES`, user is an Italian citizen) and Brazil → eligible; text open to LatAm/Brazil/anywhere → eligible (maybe if it also demands local authorization); local work authorization / no sponsorship / clearance → ineligible; Mercosur countries, sponsorship/relocation offers, or missing description → maybe; anything else in a visa country → ineligible. `required_languages()` flags languages outside `SPOKEN_LANGUAGES` that the description requires (level words near the language, or text written in German/French/Dutch). Regex heuristics — keep tests in `tests/test_eligibility.py` in sync when changing patterns.

**`ranking.py`** — `score(job, eligibility)` 0–10: Android/niche/seniority in title, stack terms in description, eligibility; penalties for junior titles, required languages and reposts.

**`tracker.py`** uses SQLite (`jobs.db`) with `url` as primary key and `sqlite3.Row` rows. `init_db()` adds later columns (`url_direct`, `description`, `fingerprint`, `country`, `eligibility`, `eligibility_reason`, `languages`, `score`, `repost_of`, `suppressed`) to existing databases and indexes `fingerprint`. Key functions: `is_new()`, `save_job(conn, job, suppressed=None)`, `first_seen()`, `get_pending_jobs()` (dicts with a `job_url` key, ordered by score), `mark_notified()`, `purge_old_jobs()`, `get_all_jobs()`.

**`notifier.py`** sends via Telegram Bot API (`parse_mode=HTML`; every dynamic field goes through `_esc()`; link previews disabled). Credentials come from `.env` (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, loaded with python-dotenv). `build_digest()` groups jobs into sections by eligibility, sorted by score, split into messages of at most `MAX_MESSAGE_CHARS`; `notify_jobs()` sends them and returns the URLs from delivered messages. `send_telegram()` waits `retry_after` on HTTP 429 and redacts the token from error output.

**`jobspy_patches.py`** and **`logger.py`** monkeypatch JobSpy/requests/tls_client at import time (Glassdoor bug workarounds and verbose Glassdoor logging).

## Key configuration points

| What | Where |
|---|---|
| Search terms | `SEARCH_TERMS` in `job_scraper.py` |
| Title keywords | `KEYWORDS` in `job_scraper.py` |
| Title blacklist | `BLACKLIST_TITLES` in `job_scraper.py` |
| Countries/regions + search mode | `REGIONS` / `GLASSDOOR_REGIONS` in `job_scraper.py` |
| LinkedIn detail fetching | `LINKEDIN_FETCH_DETAILS`, `LINKEDIN_DETAILS_*` in `job_scraper.py` |
| Eligible countries | `FREE_MOVEMENT_COUNTRIES`, `MERCOSUR_RESIDENCE_COUNTRIES` in `eligibility.py` |
| Languages the user speaks | `SPOKEN_LANGUAGES` in `eligibility.py` |
| Send ineligible jobs too | `SHOW_INELIGIBLE` in `main.py` |
| Repost window (days) | `REPOST_WINDOW_DAYS` in `main.py` |
| Schedule interval | `INTERVALO_MINUTOS` in `scheduler.py` |
| Search window (hours) | `HOURS_OLD` in `main.py` |
| History retention (days) | `HISTORY_DAYS` in `main.py` |
| Telegram credentials | `.env` → `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` |
