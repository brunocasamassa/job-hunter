import pytest

import main
import tracker


def _job(n, country="germany", company="ACME", title=None, source="indeed", description="Kotlin", **extra):
    job = {
        "job_url": f"https://example.com/jobs/{n}",
        "title": title or f"Android Engineer {n}",
        "company": company,
        "location": "Berlin, BE, DE",
        "source": source,
        "date_posted": "2026-11-06",
        "salary": "",
        "url_direct": "",
        "description": description,
        "country": country,
        "is_remote": False,
    }
    job.update(extra)
    return job


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "jobs.db")
    monkeypatch.setattr(main, "init_db", lambda: tracker.init_db(path))
    monkeypatch.setattr(main, "enrich_linkedin_details", lambda jobs: None)
    return path


@pytest.fixture
def runs(monkeypatch):
    """Cada item da lista é o resultado de fetch_jobs de uma execução."""
    batches = []
    stats = {"requests": 1, "errors": 0}
    monkeypatch.setattr(main, "fetch_jobs", lambda hours_old: (batches.pop(0), stats))
    return batches


@pytest.fixture
def sent(monkeypatch):
    """Registra o que foi para o Telegram; por padrão tudo é entregue."""
    record = {"batches": [], "hidden": [], "fail": set()}

    def fake_notify(jobs, stats=None, hidden_count=0):
        record["batches"].append([j["job_url"] for j in jobs])
        record["hidden"].append(hidden_count)
        return {j["job_url"] for j in jobs} - record["fail"]

    monkeypatch.setattr(main, "notify_jobs", fake_notify)
    return record


def test_failed_delivery_stays_pending_and_is_retried(db, runs, sent):
    runs.extend([[_job(1), _job(2)], []])
    sent["fail"].add("https://example.com/jobs/2")

    main.run()
    sent["fail"].clear()
    main.run()

    assert sent["batches"][1] == ["https://example.com/jobs/2"]
    assert tracker.get_pending_jobs(tracker.init_db(db)) == []


def test_ineligible_jobs_are_hidden_but_counted(db, runs, sent):
    us_only = _job(1, country="usa", description="Must be authorized to work in the United States.")
    runs.append([us_only, _job(2)])

    main.run()

    assert sent["batches"] == [["https://example.com/jobs/2"]]
    assert sent["hidden"] == [1]
    saved = {row["url"]: row for row in tracker.get_all_jobs(tracker.init_db(db))}
    assert saved["https://example.com/jobs/1"]["suppressed"] == "ineligible"


def test_same_job_on_two_sites_is_sent_once(db, runs, sent):
    runs.append([
        _job(1, source="linkedin", title="Senior Android Developer (m/w/d)", description=""),
        _job(2, source="indeed", title="Senior Android Developer", url_direct="https://acme.com/apply"),
    ])

    main.run()

    assert sent["batches"] == [["https://example.com/jobs/2"]]  # a versão com link direto


def test_recent_repost_is_suppressed_and_old_repost_is_tagged(db, runs, sent, monkeypatch):
    runs.extend([[_job(1, title="Android Platform Engineer")],
                 [_job(2, title="Android Platform Engineer")]])
    main.run()

    # republicada com outra URL dentro da janela → não alerta de novo
    main.run()
    assert sent["batches"][1] == []

    # fora da janela → alerta com 🔁
    monkeypatch.setattr(main, "REPOST_WINDOW_DAYS", 0)
    runs.append([_job(3, title="Android Platform Engineer")])
    main.run()
    assert sent["batches"][2] == ["https://example.com/jobs/3"]
    saved = {row["url"]: row for row in tracker.get_all_jobs(tracker.init_db(db))}
    assert saved["https://example.com/jobs/3"]["repost_of"] is not None


def test_jobs_are_classified_and_scored_before_saving(db, runs, sent):
    runs.append([_job(1, title="Senior Android Automotive Engineer", description="AAOS, VHAL")])

    main.run()

    [row] = tracker.get_all_jobs(tracker.init_db(db))
    assert row["eligibility"] == "eligible"
    assert row["score"] >= 8
    assert row["fingerprint"] == "acme|senior android automotive engineer|germany"


def test_linkedin_details_only_for_jobs_that_will_be_analyzed(db, runs, sent, monkeypatch):
    enriched = []
    monkeypatch.setattr(main, "enrich_linkedin_details", lambda jobs: enriched.extend(j["job_url"] for j in jobs))
    runs.append([
        _job(1, source="linkedin", country="germany", title="Android Dev A"),
        _job(2, source="linkedin", country="usa", title="Android Dev B", description=""),
        _job(3, source="linkedin", title="Android Dev A", description=""),  # repetida da 1
    ])

    main.run()

    # sem a repetida, e quem depende da descrição para elegibilidade (EUA) primeiro
    assert enriched == ["https://example.com/jobs/2", "https://example.com/jobs/1"]
