import pytest
import requests

import notifier


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


def _job(url="https://example.com/jobs/1", title="R&D Android <Senior>"):
    return {
        "job_url": url,
        "title": title,
        "company": "AT&T",
        "location": "Remote",
        "source": "linkedin",
        "date_posted": "2026-11-06",
        "salary": "",
    }


def test_format_escapes_html_in_fields():
    msg = notifier.format_job_message(_job(url="https://x.com/a?b=1&c=2"), 1, 1)
    assert "R&amp;D Android &lt;Senior&gt;" in msg
    assert "AT&amp;T" in msg
    assert 'href="https://x.com/a?b=1&amp;c=2"' in msg
    assert "Salário" not in msg  # salário vazio não gera linha


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
        calls.append(1)
        return FakeResponse(400, {"ok": False, "description": "can't parse entities"})

    monkeypatch.setattr(notifier.requests, "post", fake_post)
    assert notifier.send_telegram("<b>quebrado") is False
    assert len(calls) == 1


def test_network_error_does_not_print_token(monkeypatch, capsys):
    def fake_post(url, **kwargs):
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}")

    monkeypatch.setattr(notifier.requests, "post", fake_post)
    assert notifier.send_telegram("oi") is False
    assert notifier.TELEGRAM_TOKEN not in capsys.readouterr().out


def test_notify_returns_only_delivered_urls(monkeypatch):
    sent = []

    def fake_send(message):
        sent.append(message)
        return "jobs/2" not in message  # a vaga 2 falha

    monkeypatch.setattr(notifier, "send_telegram", fake_send)
    jobs = [_job("https://example.com/jobs/1"), _job("https://example.com/jobs/2")]

    delivered = notifier.notify_jobs(jobs, stats={"requests": 3, "errors": 0})

    assert delivered == {"https://example.com/jobs/1"}
    assert "não foram enviadas" in sent[-1]


def test_error_alert_escapes_and_redacts(monkeypatch):
    sent = []
    monkeypatch.setattr(notifier, "send_telegram", sent.append)

    notifier.send_error_alert(f"<html> falhou em /bot{notifier.TELEGRAM_TOKEN}/sendMessage")

    assert "&lt;html&gt;" in sent[0]
    assert notifier.TELEGRAM_TOKEN not in sent[0]
