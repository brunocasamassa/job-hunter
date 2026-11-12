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
    job_scraper._scrape_and_collect(["indeed", "linkedin"], "Germany", "Germany", 24, stats, jobs)

    assert [j["job_url"] for j in jobs] == [
        "https://de.indeed.com/viewjob?jk=1",
        "https://www.linkedin.com/jobs/view/2",
    ]
    indeed, linkedin = jobs
    assert indeed["url_direct"] == "https://careers.acme.com/apply/1"
    assert indeed["salary"] == "70,000 - 90,000 EUR/yearly"
    assert indeed["description"] == "AAOS, VHAL, Kotlin"
    assert linkedin["company"] == "N/A"
    assert linkedin["date_posted"] == "N/A"
    assert linkedin["salary"] == ""
    assert linkedin["url_direct"] == ""
    assert linkedin["description"] == ""  # vazio: enrich_linkedin_details completa depois
    assert stats == {"requests": 1, "errors": 0}
