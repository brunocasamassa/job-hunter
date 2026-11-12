from datetime import datetime, timedelta, timezone

import pytest
import requests

import ats
import radar
from ats import Board
from eligibility import EUROPE

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)


def _job(n, title="Senior Android Engineer", description="", country="germany",
         age_days=1, detail=False, **extra):
    job = {
        "title": title,
        "company": "ACME",
        "location": "Berlin",
        "job_url": f"https://ats.example/jobs/{n}",
        "source": "greenhouse",
        "date_posted": "2026-11-11",
        "salary": "",
        "url_direct": "",
        "description": description,
        "country": country,
        "is_remote": False,
        "_published_at": None if age_days is None else NOW - timedelta(days=age_days),
    }
    if detail:
        job["_detail_url"] = f"https://ats.example/api/jobs/{n}"
    job.update(extra)
    return job


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    radar._skipped_urls.clear()
    monkeypatch.setattr(radar.time, "sleep", lambda seconds: None)


@pytest.fixture
def boards(monkeypatch):
    """{nome do board: vagas ou exceção}; ats.list_jobs devolve o que estiver lá."""
    listing = {}
    monkeypatch.setattr(radar, "BOARDS", [])

    def fake_list(board, session):
        result = listing[board.token]
        if isinstance(result, Exception):
            raise result
        return [dict(job) for job in result]

    def add(token, result):
        radar.BOARDS.append(Board(token.title(), ats.GREENHOUSE, token))
        listing[token] = result

    monkeypatch.setattr(radar.ats, "list_jobs", fake_list)
    return add


@pytest.fixture
def details(monkeypatch):
    """URL da vaga → descrição que complete_job preenche (ou exceção)."""
    content, calls = {}, []

    def fake_complete(job, session):
        url = job.pop("_detail_url", None)
        if url is None:
            return
        calls.append(job["job_url"])
        result = content.get(job["job_url"], "")
        if isinstance(result, Exception):
            raise result
        job["description"] = result

    monkeypatch.setattr(radar.ats, "complete_job", fake_complete)
    return content, calls


def _fetch(known=()):
    return radar.fetch_radar_jobs(is_known=lambda url: url in known, session=object(), now=NOW)


def test_keeps_new_relevant_recent_android_jobs(boards, details, monkeypatch):
    monkeypatch.setattr(radar, "RADAR_MAX_AGE_DAYS", 14)
    boards("acme", [
        _job(1),                                         # fica
        _job(2, title="Backend Engineer"),               # título fora do filtro
        _job(3),                                         # já está no banco
        _job(4, age_days=30),                            # antiga demais
        _job(5, age_days=None),                          # sem data: fica
        _job(6, title="Junior Android Developer"),       # júnior
    ])

    jobs, stats = _fetch(known={"https://ats.example/jobs/3"})

    assert [job["job_url"].rsplit("/", 1)[1] for job in jobs] == ["1", "5"]
    assert stats == {"requests": 1, "errors": 0}
    assert all("_published_at" not in job for job in jobs)


def test_old_jobs_are_kept_by_default(boards, details):
    boards("acme", [_job(1, age_days=400)])  # vaga aberta o ano todo

    jobs, _ = _fetch()

    assert len(jobs) == 1


def test_same_role_in_several_countries_becomes_one_alert(boards, details):
    boards("finom", [
        _job(1, title="Senior Android Developer (Remote)", location="Serbia", country="serbia"),
        _job(2, title="Senior Android Developer (Remote)", location="Romania", country="romania"),
        _job(3, title="Senior Android Developer", location="Cyprus", country="cyprus"),
        _job(4, title="Android Team Lead", location="Warsaw", country="poland"),
    ])

    jobs, _ = _fetch()

    merged = [job for job in jobs if job["job_url"] != "https://ats.example/jobs/4"]
    assert {job["location"] for job in merged} == {"Serbia / Romania / Cyprus"}
    assert {job["country"] for job in merged} == {"romania"}  # o primeiro onde você pode trabalhar
    assert merged[0]["job_url"] == "https://ats.example/jobs/2"  # o dedup guarda esta: link da Romênia
    assert jobs[-1]["location"] == "Warsaw"


def test_merged_places_are_capped(boards, details, monkeypatch):
    monkeypatch.setattr(radar, "RADAR_MAX_PLACES", 2)
    boards("finom", [_job(n, location=place) for n, place in enumerate(["Poland", "Spain", "Portugal"])])

    jobs, _ = _fetch()

    assert jobs[0]["location"] == "Poland / Spain / …"


def test_automotive_title_needs_android_in_description(boards, details):
    content, calls = details
    content["https://ats.example/jobs/1"] = "Android Automotive OS apps"
    content["https://ats.example/jobs/2"] = "Sell cars to dealers"
    boards("acme", [
        _job(1, title="Automotive Software Engineer", detail=True),
        _job(2, title="Automotive Sales Manager", detail=True),
    ])

    jobs, stats = _fetch()

    assert [job["job_url"] for job in jobs] == ["https://ats.example/jobs/1"]
    assert stats["requests"] == 3  # lista + 2 descrições

    # na rodada seguinte, a vaga sem Android não busca a descrição de novo
    _fetch(known={"https://ats.example/jobs/1"})
    assert calls == ["https://ats.example/jobs/1", "https://ats.example/jobs/2"]


def test_details_are_fetched_only_for_new_relevant_jobs(boards, details):
    _, calls = details
    boards("acme", [
        _job(1, title="Android Engineer", detail=True),
        _job(2, title="Backend Engineer", detail=True),
        _job(3, title="Android Engineer II", detail=True),
    ])

    _fetch(known={"https://ats.example/jobs/3"})

    assert calls == ["https://ats.example/jobs/1"]


def test_remote_europe_description_sets_country(boards, details):
    boards("acme", [_job(1, country="", description="Android role, fully remote within the EU.")])

    [job], _ = _fetch()

    assert job["country"] == EUROPE


def test_one_failing_board_does_not_stop_the_others(boards, details):
    content, _ = details
    content["https://ats.example/jobs/3"] = requests.Timeout("slow")
    boards("down", requests.ConnectionError("offline"))
    boards("broken", ValueError("resposta inesperada"))
    boards("acme", [_job(2), _job(3, title="Android Engineer", detail=True)])

    jobs, stats = _fetch()

    assert [job["job_url"] for job in jobs] == ["https://ats.example/jobs/2"]
    assert stats == {"requests": 4, "errors": 3}


def test_boards_config_is_valid():
    known_ats = {ats.GREENHOUSE, ats.GREENHOUSE_EU, ats.LEVER, ats.LEVER_EU, ats.ASHBY}
    names = [board.company for board in radar.BOARDS]
    assert len(names) == len(set(names))
    for board in radar.BOARDS:
        assert board.ats in known_ats, board.company
        assert board.token and "/" not in board.token, board.company
        if board.params:
            assert board.ats in {ats.LEVER, ats.LEVER_EU}, board.company  # só o Lever filtra
