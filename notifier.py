# notifier.py
# Envia alerta das vagas novas via Telegram

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def send_telegram(message: str) -> bool:
    """Envia mensagem via Telegram. Retorna True se ok."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"❌ Erro ao enviar Telegram: {e}")
        return False


def format_job_message(job: dict, index: int, total: int) -> str:
    """Formata a mensagem de uma vaga para o Telegram."""
    salary = job["salary"].strip(" -")
    salary_line = f"💰 <b>Salário:</b> {salary}\n" if salary and salary != "-" else ""

    return (
        f"🤖 <b>Vaga {index}/{total} — {job['source'].upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📱 <b>{job['title']}</b>\n"
        f"🏢 {job['company']}\n"
        f"📍 {job['location']}\n"
        f"📅 {job['date_posted']}\n"
        f"{salary_line}"
        f"🔗 <a href='{job['job_url']}'>Ver vaga</a>"
    )


def notify_jobs(new_jobs: list[dict], stats: dict | None = None) -> None:
    """
    Envia resultado da execução no Telegram.
    Sempre dispara — com vagas novas mostra cada uma, sem vagas informa o status.
    """
    now = datetime.now().strftime("%H:%M • %d/%m/%Y")
    stats = stats or {}
    error_icon = "❌" if stats.get("errors", 0) > 0 else "✅"
    stats_line = (
        f"🔍 Buscas: {stats['requests']} | {error_icon} Erros: {stats['errors']}\n"
        if stats
        else ""
    )

    if not new_jobs:
        send_telegram(
            f"📭 <b>Job Hunter — nenhuma vaga nova</b>\n"
            f"⏰ {now}\n"
            f"{stats_line}"
        )
        print("📭 Nenhuma vaga nova para notificar.")
        return

    total = len(new_jobs)

    send_telegram(
        f"🔔 <b>Job Hunter — {total} vaga(s) nova(s)!</b>\n"
        f"⏰ {now}\n"
        f"{stats_line}"
        f"Android Developer • {total} resultado(s)"
    )

    for i, job in enumerate(new_jobs, start=1):
        msg = format_job_message(job, i, total)
        ok = send_telegram(msg)
        if ok:
            print(f"  📨 Enviado: {job['title']} @ {job['company']}")
        else:
            print(f"  ❌ Falha: {job['title']}")

    send_telegram("✅ Fim das vagas novas. Boa sorte nas candidaturas! 🚀")


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
        f"💥 <code>{error[:300]}</code>\n"
        f"⚠️ O bot pode ter parado. Verifique o terminal."
    )
    send_telegram(message)
