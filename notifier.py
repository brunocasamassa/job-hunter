# notifier.py
# Envia alerta das vagas novas via Telegram

import html
import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# O Telegram limita mensagens seguidas no mesmo chat: espaçamos os envios e,
# se ele responder 429, esperamos o tempo que ele pede em `retry_after`.
SEND_INTERVAL_SECONDS = 1.0
MAX_RETRIES_ON_RATE_LIMIT = 3
DEFAULT_RETRY_AFTER_SECONDS = 5


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
        "disable_web_page_preview": False,
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


def format_job_message(job: dict, index: int, total: int) -> str:
    """Formata a mensagem de uma vaga para o Telegram."""
    salary = (job.get("salary") or "").strip(" -")
    salary_line = f"💰 <b>Salário:</b> {_esc(salary)}\n" if salary else ""

    # Candidatura direto no site/ATS da empresa costuma converter melhor que
    # Easy Apply; só existe quando a vaga não é candidatura dentro do board.
    url_direct = job.get("url_direct") or ""
    direct_line = (
        f"\n🎯 <a href=\"{_esc(url_direct)}\">Aplicar no site da empresa</a>"
        if url_direct.startswith("http")
        else ""
    )

    return (
        f"🤖 <b>Vaga {index}/{total} — {_esc(str(job['source']).upper())}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📱 <b>{_esc(job['title'])}</b>\n"
        f"🏢 {_esc(job['company'])}\n"
        f"📍 {_esc(job['location'])}\n"
        f"📅 {_esc(job['date_posted'])}\n"
        f"{salary_line}"
        f"🔗 <a href=\"{_esc(job['job_url'])}\">Ver vaga</a>"
        f"{direct_line}"
    )


def notify_jobs(new_jobs: list[dict], stats: dict | None = None) -> set[str]:
    """
    Envia resultado da execução no Telegram e retorna as URLs entregues.
    Sempre dispara — com vagas novas mostra cada uma, sem vagas informa o status.
    Quem chama deve marcar como notificadas só as URLs retornadas.
    """
    now = datetime.now().strftime("%H:%M • %d/%m/%Y")
    stats = stats or {}
    error_icon = "❌" if stats.get("errors", 0) > 0 else "✅"
    stats_line = (
        f"🔍 Buscas: {stats['requests']} | {error_icon} Erros: {stats['errors']}\n"
        if stats
        else ""
    )
    delivered: set[str] = set()

    if not new_jobs:
        send_telegram(
            f"📭 <b>Job Hunter — nenhuma vaga nova</b>\n"
            f"⏰ {now}\n"
            f"{stats_line}"
        )
        print("📭 Nenhuma vaga nova para notificar.")
        return delivered

    total = len(new_jobs)

    send_telegram(
        f"🔔 <b>Job Hunter — {total} vaga(s) nova(s)!</b>\n"
        f"⏰ {now}\n"
        f"{stats_line}"
        f"Android Developer • {total} resultado(s)"
    )

    for i, job in enumerate(new_jobs, start=1):
        time.sleep(SEND_INTERVAL_SECONDS)
        if send_telegram(format_job_message(job, i, total)):
            delivered.add(job["job_url"])
            print(f"  📨 Enviado: {job['title']} @ {job['company']}")
        else:
            print(f"  ❌ Falha: {job['title']}")

    time.sleep(SEND_INTERVAL_SECONDS)
    failed = total - len(delivered)
    if failed:
        send_telegram(
            f"⚠️ {failed} vaga(s) não foram enviadas — "
            f"tento de novo na próxima execução."
        )
    else:
        send_telegram("✅ Fim das vagas novas. Boa sorte nas candidaturas! 🚀")
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
