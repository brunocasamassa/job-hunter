import pandas as pd

import job_scraper


def test_collect_builds_clean_job_dicts(monkeypatch):
    frame = pd.DataFrame([
        {
            "site": "indeed",
            "title": "Senior Android Automotive Engineer",
            "company": "ACME",
            "location": "Munich, BY, DE",
            "job_url": "https://de.indeed.com/viewjob?jk=1",
            "job_url_direct": "https://careers.acme.com/apply/1",
            "date_posted": pd.Timestamp("2026-11-06"),
            "min_amount": 70000.0,
            "max_amount": 90000.0,
            "currency": "EUR",
            "interval": "yearly",
            "description": "AAOS, VHAL, Kotlin",
            "is_remote": False,
        },
        {
            "site": "linkedin",
            "title": "Android Developer",
            "company": None,
            "location": "Lisbon, PT",
            "job_url": "https://www.linkedin.com/jobs/view/2",
            "job_url_direct": None,
            "date_posted": pd.NaT,
            "min_amount": float("nan"),
            "max_amount": float("nan"),
            "currency": None,
            "interval": None,
            "description": None,
            "is_remote": None,
        },
        {
            "site": "linkedin",
            "title": "iOS Developer",  # cai na blacklist
            "job_url": "https://www.linkedin.com/jobs/view/3",
        },
    ])
    monkeypatch.setattr(job_scraper.logger, "debug_scrape", lambda *args, **kwargs: frame)

    stats = {"requests": 0, "errors": 0}
    jobs = []
    job_scraper._scrape_and_collect(
        ["indeed", "linkedin"], "Android", "Germany", "Germany", job_scraper.ALL, 24, stats, jobs
    )

    assert [j["job_url"] for j in jobs] == [
        "https://de.indeed.com/viewjob?jk=1",
        "https://www.linkedin.com/jobs/view/2",
    ]
    indeed, linkedin = jobs
    assert indeed["url_direct"] == "https://careers.acme.com/apply/1"
    assert indeed["salary"] == "70,000 - 90,000 EUR/yearly"
    assert indeed["description"] == "AAOS, VHAL, Kotlin"
    assert indeed["country"] == "germany"
    assert indeed["is_remote"] is False
    assert linkedin["company"] == "N/A"
    assert linkedin["date_posted"] == "N/A"
    assert linkedin["salary"] == ""
    assert linkedin["url_direct"] == ""
    assert linkedin["description"] == ""  # vazio: enrich_linkedin_details completa depois
    assert linkedin["is_remote"] is False
    assert stats == {"requests": 1, "errors": 0}


def test_fetch_runs_every_term_in_every_region_with_its_mode(monkeypatch):
    calls = []

    def fake_debug_scrape(site_names, search_term, location, country_indeed, hours_old,
                          is_remote=False):
        calls.append((tuple(site_names), search_term, location, is_remote))
        return pd.DataFrame()

    monkeypatch.setattr(job_scraper.logger, "debug_scrape", fake_debug_scrape)
    monkeypatch.setattr(job_scraper, "SEARCH_TERMS", ["Android", "AAOS"])
    monkeypatch.setattr(job_scraper, "REGIONS", [
        ("Germany", "Germany", job_scraper.ALL),
        ("United States", "USA", job_scraper.REMOTE),
    ])
    monkeypatch.setattr(job_scraper, "GLASSDOOR_REGIONS", [
        ("Germany", "Germany", job_scraper.ALL),
    ])

    jobs, stats = job_scraper.fetch_jobs(hours_old=24)

    assert jobs == []
    assert stats == {"requests": 6, "errors": 0}
    assert calls == [
        (("indeed", "linkedin"), "Android", "Germany", False),
        (("indeed", "linkedin"), "Android", "United States", True),
        (("glassdoor",), "Android", "Germany", False),
        (("indeed", "linkedin"), "AAOS", "Germany", False),
        (("indeed", "linkedin"), "AAOS", "United States", True),
        (("glassdoor",), "AAOS", "Germany", False),
    ]


def test_every_region_has_a_valid_mode():
    for location, country, mode in job_scraper.REGIONS + job_scraper.GLASSDOOR_REGIONS:
        assert mode in {job_scraper.ALL, job_scraper.REMOTE}, location
