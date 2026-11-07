import pytest

import job_scraper


def _li(job_id, **overrides):
    job = {
        "job_url": f"https://www.linkedin.com/jobs/view/{job_id}",
        "source": "linkedin",
        "description": "",
        "url_direct": "",
    }
    job.update(overrides)
    return job


@pytest.fixture
def fake_linkedin(monkeypatch):
    """Troca o scraper do JobSpy por um falso; `responses` mapeia job_id -> detalhes."""
    responses = {}
    calls = []

    class FakeLinkedIn:
        scraper_input = None

        def _get_job_details(self, job_id):
            calls.append(job_id)
            return responses.get(job_id, {})

    monkeypatch.setattr(job_scraper, "LinkedIn", FakeLinkedIn)
    monkeypatch.setattr(job_scraper.time, "sleep", lambda seconds: None)
    return responses, calls


def test_fills_description_and_direct_url_only_for_linkedin(fake_linkedin):
    responses, calls = fake_linkedin
    responses["111"] = {"description": "AAOS, Kotlin", "job_url_direct": "https://careers.acme.com/1"}
    indeed = {"job_url": "https://indeed.com/x", "source": "indeed", "description": ""}
    jobs = [_li("111"), indeed]

    stats = job_scraper.enrich_linkedin_details(jobs)

    assert calls == ["111"]
    assert jobs[0]["description"] == "AAOS, Kotlin"
    assert jobs[0]["url_direct"] == "https://careers.acme.com/1"
    assert stats == {"fetched": 1, "failed": 0, "skipped": 0}


def test_stops_after_consecutive_failures(fake_linkedin, monkeypatch):
    _, calls = fake_linkedin  # sem respostas: toda chamada falha ({})
    monkeypatch.setattr(job_scraper, "LINKEDIN_DETAILS_MAX_CONSECUTIVE_FAILURES", 3)
    jobs = [_li(str(n)) for n in range(10)]

    stats = job_scraper.enrich_linkedin_details(jobs)

    assert len(calls) == 3
    assert stats == {"fetched": 0, "failed": 3, "skipped": 7}


def test_respects_max_per_run(fake_linkedin, monkeypatch):
    responses, calls = fake_linkedin
    for n in range(5):
        responses[str(n)] = {"description": f"vaga {n}"}
    monkeypatch.setattr(job_scraper, "LINKEDIN_DETAILS_MAX_PER_RUN", 2)

    stats = job_scraper.enrich_linkedin_details([_li(str(n)) for n in range(5)])

    assert calls == ["0", "1"]
    assert stats == {"fetched": 2, "failed": 0, "skipped": 3}


def test_disabled_flag_makes_no_requests(fake_linkedin, monkeypatch):
    _, calls = fake_linkedin
    monkeypatch.setattr(job_scraper, "LINKEDIN_FETCH_DETAILS", False)

    stats = job_scraper.enrich_linkedin_details([_li("1"), _li("2")])

    assert calls == []
    assert stats["skipped"] == 2


def test_jobs_with_description_are_not_refetched(fake_linkedin):
    _, calls = fake_linkedin
    job_scraper.enrich_linkedin_details([_li("1", description="já veio")])
    assert calls == []


def test_real_jobspy_class_accepts_our_scraper_input():
    """Garante que o JobSpy instalado ainda tem a API interna que usamos."""
    scraper = job_scraper.LinkedIn()
    scraper.scraper_input = job_scraper.ScraperInput(site_type=[job_scraper.Site.LINKEDIN])
    assert callable(getattr(scraper, "_get_job_details", None))
