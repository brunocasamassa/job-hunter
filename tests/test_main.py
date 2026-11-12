import main
import tracker


def _job(n):
    return {
        "job_url": f"https://example.com/jobs/{n}",
        "title": f"Android Engineer {n}",
        "company": "ACME",
        "location": "Berlin, BE, DE",
        "source": "indeed",
        "date_posted": "2026-11-06",
        "salary": "",
        "url_direct": "",
        "description": "",
    }


def test_failed_delivery_stays_pending_and_is_retried(tmp_path, monkeypatch):
    db_path = str(tmp_path / "jobs.db")
    monkeypatch.setattr(main, "init_db", lambda: tracker.init_db(db_path))

    stats = {"requests": 1, "errors": 0}
    runs = iter([[_job(1), _job(2)], []])
    monkeypatch.setattr(main, "fetch_jobs", lambda hours_old: (next(runs), stats))
    monkeypatch.setattr(main, "enrich_linkedin_details", lambda jobs: None)

    sent_batches = []

    def fake_notify(jobs, stats=None):
        sent_batches.append([j["job_url"] for j in jobs])
        # 1ª execução: só a vaga 1 chega; 2ª: tudo chega
        if len(sent_batches) == 1:
            return {"https://example.com/jobs/1"}
        return {j["job_url"] for j in jobs}

    monkeypatch.setattr(main, "notify_jobs", fake_notify)

    main.run()  # vaga 2 falha no envio
    main.run()  # nenhuma vaga nova, mas a 2 é reenviada

    assert sent_batches == [
        ["https://example.com/jobs/1", "https://example.com/jobs/2"],
        ["https://example.com/jobs/2"],
    ]
    conn = tracker.init_db(db_path)
    assert tracker.get_pending_jobs(conn) == []


def test_linkedin_details_are_saved_with_new_jobs(tmp_path, monkeypatch):
    db_path = str(tmp_path / "jobs.db")
    monkeypatch.setattr(main, "init_db", lambda: tracker.init_db(db_path))
    monkeypatch.setattr(main, "fetch_jobs", lambda hours_old: ([_job(1)], {"requests": 1, "errors": 0}))

    def fake_enrich(jobs):
        for job in jobs:
            job["url_direct"] = "https://careers.acme.com/apply/1"

    monkeypatch.setattr(main, "enrich_linkedin_details", fake_enrich)
    monkeypatch.setattr(main, "notify_jobs", lambda jobs, stats=None: set())  # tudo falha

    main.run()

    conn = tracker.init_db(db_path)
    assert tracker.get_pending_jobs(conn)[0]["url_direct"] == "https://careers.acme.com/apply/1"
