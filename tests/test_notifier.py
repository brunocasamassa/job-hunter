import pytest
import requests

import notifier
from eligibility import ELIGIBLE, INELIGIBLE, MAYBE


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(notifier.time, "sleep", sleeps.append)
    return sleeps


def _job(url="https://example.com/jobs/1", title="R&D Android <Senior>", **extra):
    job = {
        "job_url": url,
        "title": title,
        "company": "AT&T",
        "location": "Remote",
        "source": "linkedin",
        "date_posted": "2026-11-06",
        "salary": "",
    }
    job.update(extra)
    return job


# ── Bloco de uma vaga ────────────────────────────────────────────────────────

def test_block_escapes_html_in_fields():
    block = notifier.format_job_block(_job(url="https://x.com/a?b=1&c=2"), 1)
    assert "R&amp;D Android &lt;Senior&gt;" in block
    assert "AT&amp;T" in block
    assert 'href="https://x.com/a?b=1&amp;c=2"' in block
    assert "💰" not in block  # salário vazio não gera tag


def test_block_shows_tags_and_direct_link():
    block = notifier.format_job_block(_job(
        score=8,
        eligibility_reason="🇪🇺 UE/EEE/Suíça — sem visto",
        languages="german,french",
        repost_of="2026-09-01",
        url_direct="https://careers.acme.com/1",
        salary="70,000 - 90,000 EUR/yearly",
    ), 3)
    assert block.startswith("3. ⭐8 <b>")
    assert "🗣️ exige alemão, francês" in block
    assert "🔁 já vista em 2026-09-01" in block
    assert "💰 70,000 - 90,000 EUR/yearly" in block
    assert 'href="https://careers.acme.com/1">🎯 Aplicar no site da empresa' in block


def test_block_from_legacy_row_has_no_score_or_direct_link():
    block = notifier.format_job_block(_job(score=None, url_direct=None), 1)
    assert "⭐" not in block
    assert "Aplicar no site da empresa" not in block


# ── Resumo ───────────────────────────────────────────────────────────────────

def test_digest_groups_by_eligibility_and_sorts_by_score():
    jobs = [
        _job("u/maybe", "Maybe", eligibility=MAYBE, score=9),
        _job("u/low", "Low", eligibility=ELIGIBLE, score=4),
        _job("u/high", "High", eligibility=ELIGIBLE, score=8),
        _job("u/legacy", "Legacy"),  # sem elegibilidade (linha antiga) → confira
    ]
    [(text, urls)] = notifier.build_digest(jobs, stats={"requests": 5, "errors": 0}, hidden_count=7)

    assert urls == ["u/high", "u/low", "u/maybe", "u/legacy"]
    assert text.index("Pode aplicar") < text.index("High") < text.index("Low")
    assert text.index("Low") < text.index("Confira antes") < text.index("Maybe")
    assert "🙈 7 oculta(s)" in text
    assert "Exige visto" not in text  # sem vagas inelegíveis, sem seção


# -1: data em UTC já no dia seguinte ao do Brasil.
@pytest.mark.parametrize("days_ago, tag", [(-1, "📅 hoje"), (0, "📅 hoje"), (1, "📅 há 1 dia"), (12, "📅 há 12 dias")])
def test_job_block_shows_how_old_the_job_is(days_ago, tag):
    from datetime import date, timedelta
    posted = (date.today() - timedelta(days=days_ago)).isoformat()
    assert tag in notifier.format_job_block(_job(date_posted=posted), 1)


@pytest.mark.parametrize("date_posted", ["N/A", "", None, "2999-01-01"])
def test_job_block_without_valid_date_has_no_age(date_posted):
    assert "📅" not in notifier.format_job_block(_job(date_posted=date_posted), 1)


def test_digest_header_uses_the_title():
    [(default, _)] = notifier.build_digest([_job(eligibility=ELIGIBLE)])
    [(radar, _)] = notifier.build_digest([_job(eligibility=ELIGIBLE)], title="📡 Radar")

    assert default.startswith("<b>🔔 Job Hunter — 1 vaga(s)</b>")
    assert radar.startswith("<b>📡 Radar — 1 vaga(s)</b>")


def test_digest_splits_long_lists_within_limit():
    jobs = [_job(f"u/{n}", f"Android Engineer {n}", eligibility=ELIGIBLE, score=5) for n in range(40)]
    messages = notifier.build_digest(jobs)

    assert len(messages) > 1
    assert all(len(text) <= notifier.MAX_MESSAGE_CHARS for text, _ in messages)
    assert [url for _, urls in messages for url in urls] == [f"u/{n}" for n in range(40)]
    assert messages[1][0].startswith("<i>(continuação)</i>\n\n✅ <b>Pode aplicar</b>")


def test_digest_shows_ineligible_section_when_present():
    [(text, _)] = notifier.build_digest([_job(eligibility=INELIGIBLE, score=1)])
    assert "❌ <b>Exige visto/residência</b>" in text


def test_notify_returns_urls_only_from_delivered_messages(monkeypatch):
    jobs = [_job(f"u/{n}", f"Android Engineer {n}", eligibility=ELIGIBLE, score=5) for n in range(40)]
    messages = notifier.build_digest(jobs)
    calls = []

    def fake_send(text):
        calls.append(text)
        return len(calls) != 2  # a 2ª mensagem falha

    monkeypatch.setattr(notifier, "send_telegram", fake_send)
    delivered = notifier.notify_jobs(jobs)

    expected = set(messages[0][1]) | {url for _, urls in messages[2:] for url in urls}
    assert delivered == expected
    assert not set(messages[1][1]) & delivered


def test_notify_without_jobs_sends_status(monkeypatch):
    sent = []
    monkeypatch.setattr(notifier, "send_telegram", sent.append)

    assert notifier.notify_jobs([], stats={"requests": 3, "errors": 1}, hidden_count=2) == set()
    assert "nenhuma vaga nova" in sent[0]
    assert "🙈 2 oculta(s)" in sent[0]


# ── Envio ────────────────────────────────────────────────────────────────────

def test_send_retries_after_429_then_succeeds(monkeypatch, no_sleep):
    responses = [
        FakeResponse(429, {"ok": False, "parameters": {"retry_after": 2}}),
        FakeResponse(200, {"ok": True}),
    ]
    monkeypatch.setattr(notifier.requests, "post", lambda *a, **k: responses.pop(0))

    assert notifier.send_telegram("oi") is True
    assert no_sleep == [2]


def test_send_does_not_retry_on_bad_request(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        return FakeResponse(400, {"ok": False, "description": "can't parse entities"})

    monkeypatch.setattr(notifier.requests, "post", fake_post)
    assert notifier.send_telegram("<b>quebrado") is False
    assert len(calls) == 1
    assert calls[0]["link_preview_options"] == {"is_disabled": True}


def test_network_error_does_not_print_token(monkeypatch, capsys):
    def fake_post(url, **kwargs):
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}")

    monkeypatch.setattr(notifier.requests, "post", fake_post)
    assert notifier.send_telegram("oi") is False
    assert notifier.TELEGRAM_TOKEN not in capsys.readouterr().out


def test_error_alert_escapes_and_redacts(monkeypatch):
    sent = []
    monkeypatch.setattr(notifier, "send_telegram", sent.append)

    notifier.send_error_alert(f"<html> falhou em /bot{notifier.TELEGRAM_TOKEN}/sendMessage")

    assert "&lt;html&gt;" in sent[0]
    assert notifier.TELEGRAM_TOKEN not in sent[0]
