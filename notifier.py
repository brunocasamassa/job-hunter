# notifier.py
# Envia alerta das vagas novas via Telegram

import html
import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

from eligibility import ELIGIBLE, INELIGIBLE, LANGUAGE_LABELS, MAYBE

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# O Telegram limita mensagens seguidas no mesmo chat: espaçamos os envios e,
# se ele responder 429, esperamos o tempo que ele pede em `retry_after`.
SEND_INTERVAL_SECONDS = 1.0
MAX_RETRIES_ON_RATE_LIMIT = 3
DEFAULT_RETRY_AFTER_SECONDS = 5

# O Telegram aceita até 4096 caracteres por mensagem; sobra folga.
MAX_MESSAGE_CHARS = 3800

_SECTIONS = (
    (ELIGIBLE,   "✅ <b>Pode aplicar</b>"),
    (MAYBE,      "⚠️ <b>Confira antes</b>"),
    (INELIGIBLE, "❌ <b>Exige visto/residência</b>"),
)


def _esc(value) -> str:
    """Escapa texto para o parse_mode HTML (um '&' cru faz o Telegram recusar a mensagem)."""
    return html.escape("" if value is None else str(value), quote=True)


def _redact(text: str) -> str:
    """Tira o token de mensagens de erro: exceções do requests incluem a URL."""
    return text.replace(TELEGRAM_TOKEN, "***") if TELEGRAM_TOKEN else text


def _retry_after_seconds(resp: requests.Response) -> int:
    try:
        return int(resp.json()["parameters"]["retry_after"])
    except (ValueError, KeyError, TypeError):
        return DEFAULT_RETRY_AFTER_SECONDS


def _error_description(resp: requests.Response) -> str:
    try:
        return str(resp.json().get("description", ""))
    except (ValueError, AttributeError):
        return resp.text[:200]


def send_telegram(message: str) -> bool:
    """Envia mensagem via Telegram. Retorna True se ok."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        # Resumo tem vários links; a prévia do primeiro só polui a mensagem.
        "link_preview_options": {"is_disabled": True},
    }
    for attempt in range(MAX_RETRIES_ON_RATE_LIMIT + 1):
        try:
            resp = requests.post(url, json=payload, timeout=10)
        except requests.RequestException as e:
            print(f"❌ Erro ao enviar Telegram: {_redact(str(e))}")
            return False

        if resp.status_code == 200:
            return True
        if resp.status_code == 429 and attempt < MAX_RETRIES_ON_RATE_LIMIT:
            wait = _retry_after_seconds(resp)
            print(f"⏳ Telegram pediu pausa de {wait}s (429). Tentando de novo...")
            time.sleep(wait)
            continue

        print(f"❌ Telegram recusou a mensagem ({resp.status_code}): {_error_description(resp)}")
        return False
    return False


def _language_tag(codes: str | None) -> str:
    names = [LANGUAGE_LABELS.get(code, code) for code in (codes or "").split(",") if code]
    return f"🗣️ exige {', '.join(names)}" if names else ""


def format_job_block(job: dict, position: int) -> str:
    """Bloco de uma vaga dentro do resumo."""
    salary = (job.get("salary") or "").strip(" -")
    tags = [
        job.get("eligibility_reason") or "",
        _language_tag(job.get("languages")),
        f"🔁 já vista em {job['repost_of']}" if job.get("repost_of") else "",
        f"💰 {salary}" if salary else "",
    ]
    links = [f"<a href=\"{_esc(job['job_url'])}\">Ver vaga</a>"]
    url_direct = job.get("url_direct") or ""
    if url_direct.startswith("http"):
        links.append(f"<a href=\"{_esc(url_direct)}\">🎯 Aplicar no site da empresa</a>")

    score = job.get("score")
    score_tag = f"⭐{_esc(score)} " if score is not None else ""
    lines = [
        f"{position}. {score_tag}<b>{_esc(job['title'])}</b>",
        f"🏢 {_esc(job['company'])} · 📍 {_esc(job['location'])} · {_esc(str(job['source']).upper())}",
    ]
    tag_line = " · ".join(_esc(tag) for tag in tags if tag)
    if tag_line:
        lines.append(tag_line)
    lines.append("🔗 " + " · ".join(links))
    return "\n".join(lines)


def _status_line(stats: dict | None, hidden_count: int) -> str:
    lines = []
    if stats:
        error_icon = "❌" if stats.get("errors", 0) > 0 else "✅"
        lines.append(f"🔍 Buscas: {stats['requests']} | {error_icon} Erros: {stats['errors']}")
    if hidden_count:
        lines.append(f"🙈 {hidden_count} oculta(s): exigem visto/residência")
    return "\n".join(lines)


def build_digest(jobs: list[dict], stats: dict | None = None,
                 hidden_count: int = 0) -> list[tuple[str, list[str]]]:
    """
    Resumo das vagas: seções por elegibilidade, maior nota primeiro.
    Retorna [(mensagem, urls_das_vagas_nela)], cada mensagem dentro do limite.
    """
    now = datetime.now().strftime("%H:%M • %d/%m/%Y")
    header = f"🔔 <b>Job Hunter — {len(jobs)} vaga(s)</b>\n⏰ {now}"
    status = _status_line(stats, hidden_count)
    if status:
        header += f"\n{status}"

    messages: list[tuple[str, list[str]]] = []
    text, urls = header, []
    position = 0
    for section_status, section_title in _SECTIONS:
        group = [job for job in jobs if (job.get("eligibility") or MAYBE) == section_status]
        group.sort(key=lambda job: job.get("score") or 0, reverse=True)
        for index, job in enumerate(group):
            position += 1
            block = format_job_block(job, position)
            chunk = (f"\n\n{section_title}" if index == 0 else "") + f"\n\n{block}"
            if urls and len(text) + len(chunk) > MAX_MESSAGE_CHARS:
                messages.append((text, urls))
                text, urls = "<i>(continuação)</i>", []
                chunk = f"\n\n{section_title}\n\n{block}"
            text += chunk
            urls.append(job["job_url"])
    messages.append((text, urls))
    return messages


def notify_jobs(new_jobs: list[dict], stats: dict | None = None,
                hidden_count: int = 0) -> set[str]:
    """
    Envia o resumo no Telegram e retorna as URLs entregues.
    Sempre dispara — sem vagas, informa o status da execução.
    Quem chama deve marcar como notificadas só as URLs retornadas.
    """
    if not new_jobs:
        now = datetime.now().strftime("%H:%M • %d/%m/%Y")
        status = _status_line(stats, hidden_count)
        send_telegram(
            f"📭 <b>Job Hunter — nenhuma vaga nova</b>\n⏰ {now}"
            + (f"\n{status}" if status else "")
        )
        print("📭 Nenhuma vaga nova para notificar.")
        return set()

    delivered: set[str] = set()
    messages = build_digest(new_jobs, stats=stats, hidden_count=hidden_count)
    for index, (text, urls) in enumerate(messages, start=1):
        if index > 1:
            time.sleep(SEND_INTERVAL_SECONDS)
        if send_telegram(text):
            delivered.update(urls)
            print(f"  📨 Mensagem {index}/{len(messages)}: {len(urls)} vaga(s)")
        else:
            print(f"  ❌ Mensagem {index}/{len(messages)} falhou — {len(urls)} vaga(s) ficam pendentes")
    return delivered


def send_heartbeat(stats: dict) -> None:
    """Envia sinal de vida ao final de cada execução."""
    now = datetime.now().strftime("%H:%M • %d/%m/%Y")
    error_icon = "❌" if stats["errors"] > 0 else "✅"
    jobs_line = (
        f"🆕 {stats['new_jobs']} vaga(s) nova(s)"
        if stats["new_jobs"] > 0
        else "📭 Nenhuma vaga nova"
    )

    message = (
        f"🟢 <b>Job Hunter — ativo</b>\n"
        f"⏰ {now}\n"
        f"🔍 Buscas: {stats['requests']} | {error_icon} Erros: {stats['errors']}\n"
        f"{jobs_line}"
    )
    send_telegram(message)


def send_error_alert(error: str) -> None:
    """Envia alerta de erro crítico (crash inesperado)."""
    now = datetime.now().strftime("%H:%M • %d/%m/%Y")
    message = (
        f"🔴 <b>Job Hunter — ERRO CRÍTICO</b>\n"
        f"⏰ {now}\n"
        f"💥 <code>{_esc(_redact(error)[:300])}</code>\n"
        f"⚠️ O bot pode ter parado. Verifique o terminal."
    )
    send_telegram(message)
