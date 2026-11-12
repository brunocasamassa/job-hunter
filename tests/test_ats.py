from datetime import datetime, timezone

import pytest
import requests

import ats
from ats import ASHBY, GREENHOUSE, GREENHOUSE_EU, LEVER, LEVER_EU, Board


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    """Responde por URL (sem querystring); URL desconhecida → 404."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append((url, params))
        return self.routes.get(url, FakeResponse(404, {"error": "not found"}))


def _ms(*args):
    return int(datetime(*args, tzinfo=timezone.utc).timestamp() * 1000)


# Formatos como os das APIs reais (campos conferidos em nov/2026).
GREENHOUSE_LIST = {
    "jobs": [
        {
            "id": 111,
            "title": "Senior Android Engineer",
            "absolute_url": "https://job-boards.greenhouse.io/monzo/jobs/111",
            "location": {"name": "Barcelona"},
            "updated_at": "2026-11-12T10:00:00-05:00",
            "first_published": "2026-11-10T09:00:00-05:00",
            "company_name": "Monzo",
        },
        {"id": 222, "title": "", "absolute_url": "https://job-boards.greenhouse.io/monzo/jobs/222"},
        "not a job",
    ],
    "meta": {"total": 2},
}
GREENHOUSE_DETAIL = {
    "id": 111,
    "content": "&lt;p&gt;Build our &lt;b&gt;Android&lt;/b&gt; app &amp;amp; more.&lt;/p&gt;"
               "&lt;ul&gt;&lt;li&gt;Kotlin&lt;/li&gt;&lt;/ul&gt;",
    "offices": [{"name": "Barcelona", "location": "Barcelona, Spain"}],
}
LEVER_LIST = [
    {
        "id": "abc",
        "text": "Senior Android Engineer",
        "hostedUrl": "https://jobs.eu.lever.co/tomtom/abc",
        "applyUrl": "https://jobs.eu.lever.co/tomtom/abc/apply",
        "categories": {
            "commitment": "Employee, Full Time",
            "location": "Belgrade, Serbia",
            "team": "Apps",
            "allLocations": ["Belgrade, Serbia", "Amsterdam, The Netherlands"],
        },
        "country": "RS",
        "workplaceType": "hybrid",
        "createdAt": _ms(2026, 11, 10, 12),
        "descriptionPlain": "Build Android apps for cars.",
        "lists": [{"text": "What you'll need", "content": "<li>Kotlin</li><li>AAOS</li>"}],
        "additionalPlain": "Apply now.",
        "salaryRange": {"currency": "EUR", "interval": "per-year-salary", "min": 70000, "max": 90000},
    },
    {"id": "no-url", "text": "Android Engineer"},
]
ASHBY_LIST = {
    "jobs": [
        {
            "id": "u1",
            "title": "Senior Android Engineer, Auto Integration",
            "location": "Helsinki",
            "secondaryLocations": [
                {"location": "Remote - US", "address": {"postalAddress": {"addressCountry": "United States"}}},
            ],
            "isListed": True,
            "isRemote": False,
            "workplaceType": "Hybrid",
            "publishedAt": "2026-11-11T08:00:00.023+00:00",
            "address": {"postalAddress": {"addressCountry": "Finland", "addressLocality": "Helsinki"}},
            "jobUrl": "https://jobs.ashbyhq.com/Mapbox/u1",
            "applyUrl": "https://jobs.ashbyhq.com/Mapbox/u1/application",
            "descriptionPlain": "Android Automotive navigation.",
            "compensation": {"compensationTierSummary": "€70K – €90K"},
        },
        {"id": "u2", "title": "Hidden", "isListed": False, "jobUrl": "https://jobs.ashbyhq.com/Mapbox/u2"},
    ],
}


def test_html_to_text():
    markup = "<p>Hello &amp; <b>world</b></p><ul><li>one</li><li> two </li></ul>"
    assert ats.html_to_text(markup) == "Hello & world\none\ntwo"


def test_greenhouse_list_and_details():
    board = Board("Monzo", GREENHOUSE, "monzo")
    session = FakeSession({
        "https://boards-api.greenhouse.io/v1/boards/monzo/jobs": FakeResponse(200, GREENHOUSE_LIST),
        "https://boards-api.greenhouse.io/v1/boards/monzo/jobs/111": FakeResponse(200, GREENHOUSE_DETAIL),
    })

    [job] = ats.list_jobs(board, session)

    assert job["title"] == "Senior Android Engineer"
    assert job["company"] == "Monzo"
    assert job["job_url"] == "https://job-boards.greenhouse.io/monzo/jobs/111"
    assert job["source"] == "greenhouse"
    assert job["location"] == "Barcelona"
    assert job["country"] == "spain"
    assert job["date_posted"] == "2026-11-10"  # first_published, não updated_at
    assert job["description"] == ""             # a lista vem sem descrição
    assert session.calls[0][1] == {}            # sem content=true

    ats.complete_job(job, session)

    assert job["description"] == "Build our Android app & more.\nKotlin"
    assert "_detail_url" not in job
    ats.complete_job(job, session)  # já completa: não busca de novo
    assert len(session.calls) == 2


def test_greenhouse_falls_back_to_the_other_region():
    board = Board("Paradox Cat", GREENHOUSE, "paradoxcatgmbh")
    session = FakeSession({
        "https://boards-api.eu.greenhouse.io/v1/boards/paradoxcatgmbh/jobs": FakeResponse(200, GREENHOUSE_LIST),
    })

    [job] = ats.list_jobs(board, session)

    assert job["_detail_url"].startswith("https://boards-api.eu.greenhouse.io/")


def test_errors_other_than_404_do_not_switch_region():
    board = Board("Monzo", GREENHOUSE_EU, "monzo")
    session = FakeSession({
        "https://boards-api.eu.greenhouse.io/v1/boards/monzo/jobs": FakeResponse(500, {}),
    })

    with pytest.raises(requests.HTTPError):
        ats.list_jobs(board, session)
    assert len(session.calls) == 1


def test_lever_postings():
    board = Board("TomTom", LEVER_EU, "tomtom", {"team": "Apps"})
    session = FakeSession({"https://api.eu.lever.co/v0/postings/tomtom": FakeResponse(200, LEVER_LIST)})

    [job] = ats.list_jobs(board, session)

    assert session.calls[0][1] == {"mode": "json", "team": "Apps"}
    assert job["title"] == "Senior Android Engineer"
    assert job["source"] == "lever"
    assert job["location"] == "Belgrade, Serbia / Amsterdam, The Netherlands"
    assert job["country"] == "netherlands"  # prefere o local na UE ao código RS
    assert job["is_remote"] is False
    assert job["date_posted"] == "2026-11-10"
    assert job["url_direct"] == "https://jobs.eu.lever.co/tomtom/abc/apply"
    assert job["salary"] == "70,000 - 90,000 EUR/year"
    assert "Build Android apps for cars." in job["description"]
    assert "What you'll need\nKotlin\nAAOS" in job["description"]
    assert job["description"].endswith("Apply now.")
    assert "_detail_url" not in job


def test_ashby_postings():
    board = Board("Mapbox", ASHBY, "Mapbox")
    session = FakeSession({
        "https://api.ashbyhq.com/posting-api/job-board/Mapbox": FakeResponse(200, ASHBY_LIST),
    })

    [job] = ats.list_jobs(board, session)

    assert session.calls[0][1] == {"includeCompensation": "true"}
    assert job["source"] == "ashby"
    assert job["location"] == "Helsinki / Remote - US"
    assert job["country"] == "finland"
    assert job["date_posted"] == "2026-11-11"
    assert job["salary"] == "€70K – €90K"
    assert job["description"] == "Android Automotive navigation."
    assert job["url_direct"].endswith("/application")


@pytest.mark.parametrize("board, url, payload", [
    (Board("TomTom", LEVER, "tomtom"), "https://api.lever.co/v0/postings/tomtom", {"ok": False}),
    (Board("Mapbox", ASHBY, "Mapbox"), "https://api.ashbyhq.com/posting-api/job-board/Mapbox", []),
    (Board("Monzo", GREENHOUSE, "monzo"), "https://boards-api.greenhouse.io/v1/boards/monzo/jobs", {"x": 1}),
])
def test_unexpected_payload_raises_value_error(board, url, payload):
    with pytest.raises(ValueError):
        ats.list_jobs(board, FakeSession({url: FakeResponse(200, payload)}))


def test_invalid_json_raises_value_error():
    board = Board("Mapbox", ASHBY, "Mapbox")
    session = FakeSession({
        "https://api.ashbyhq.com/posting-api/job-board/Mapbox": FakeResponse(200, ValueError("bad json")),
    })
    with pytest.raises(ValueError):
        ats.list_jobs(board, session)


def test_unknown_ats_raises_value_error():
    with pytest.raises(ValueError):
        ats.list_jobs(Board("X", "workday", "x"), FakeSession({}))
