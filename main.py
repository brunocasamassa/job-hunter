# main.py
# Orquestra scraping → filtragem → banco → notificação

import sys
from contextlib import closing
from datetime import datetime

from dedupe import fingerprint, split_duplicates
from eligibility import FREE_MOVEMENT_COUNTRIES, HOME_COUNTRY, INELIGIBLE, classify
from job_scraper import fetch_jobs, enrich_linkedin_details
from notifier import notify_jobs, send_error_alert
from radar import fetch_radar_jobs
from ranking import score
from tracker import (
    first_seen, get_pending_jobs, init_db, is_new, mark_notified, purge_old_jobs, save_job,
)

# Quanto tempo lembrar das vagas já vistas. Com 10 dias, uma vaga republicada
# com a mesma URL voltava como "nova"; o banco é pequeno, dá para guardar mais.
HISTORY_DAYS = 180

# Janela da busca: só vagas publicadas nas últimas N horas.
HOURS_OLD = 24

# Vagas que exigem visto/residência: False = não manda, só conta no resumo
# (ficam no banco com suppressed = "ineligible").
SHOW_INELIGIBLE = False

# Mesma empresa + título + país já vista há menos que isso: não repete o alerta.
# Há mais tempo: alerta de novo com 🔁 (republicação — às vezes vaga fantasma).
REPOST_WINDOW_DAYS = 30


def _days_since(iso_timestamp: str) -> float:
    try:
        seen = datetime.fromisoformat(iso_timestamp)
    except ValueError:
        return float("inf")
    return (datetime.now() - seen).total_seconds() / 86400


def _description_matters_most(job: dict) -> int:
    """Ordem dos detalhes do LinkedIn: onde a descrição decide a elegibilidade vem antes."""
    country = job.get("country") or ""
    return 1 if country in FREE_MOVEMENT_COUNTRIES or country == HOME_COUNTRY else 0


def process_new_jobs(conn, new_jobs: list[dict]) -> dict:
    """
    Deduplica, completa, classifica, pontua e salva as vagas novas.
    Retorna contagens: {"to_send", "hidden", "duplicates", "reposts"}.
    """
    counts = {"to_send": 0, "hidden": 0, "duplicates": 0, "reposts": 0}

    for job in new_jobs:
        job["fingerprint"] = fingerprint(job)
    unique, duplicates = split_duplicates(new_jobs)

    candidates = []
    for job in unique:
        seen_at = first_seen(conn, job["fingerprint"]) if job["fingerprint"] else None
        if seen_at is not None and _days_since(seen_at) < REPOST_WINDOW_DAYS:
            duplicates.append(job)  # já alertada há pouco por outro site/URL
            continue
        if seen_at is not None:
            job["repost_of"] = seen_at[:10]
            counts["reposts"] += 1
        candidates.append(job)

    # Detalhes do LinkedIn (descrição + link do site da empresa) só para quem
    # sobrou: cada vaga custa 1 request e o LinkedIn limita por IP.
    enrich_linkedin_details(sorted(candidates, key=_description_matters_most))

    for job in candidates:
        result = classify(job)
        job["eligibility"] = result.status
        job["eligibility_reason"] = result.reason
        job["languages"] = ",".join(result.languages)
        job["score"] = score(job, result)
        if result.status == INELIGIBLE and not SHOW_INELIGIBLE:
            save_job(conn, job, suppressed="ineligible")
            counts["hidden"] += 1
        else:
            save_job(conn, job)
            counts["to_send"] += 1

    for job in duplicates:
        save_job(conn, job, suppressed="duplicate")
    counts["duplicates"] = len(duplicates)
    return counts


def run():
    print("\n" + "=" * 45)
    print("  🤖 JOB HUNTER — Android Developer")
    print("=" * 45 + "\n")

    try:
        with closing(init_db()) as conn:
            # 1. Limpa registros muito antigos
            deleted = purge_old_jobs(conn, days=HISTORY_DAYS)
            if deleted:
                print(f"🗑️  {deleted} vaga(s) antigas removidas do cache.")

            # 2. Busca vagas
            jobs, scraper_stats = fetch_jobs(hours_old=HOURS_OLD)

            # 3. Novas (URL nunca vista) → dedup, detalhes, elegibilidade, nota
            new_jobs = [job for job in jobs if is_new(conn, job["job_url"])]
            counts = process_new_jobs(conn, new_jobs)
            print(
                f"\n🆕 {len(new_jobs)} vaga(s) nova(s): {counts['to_send']} para enviar, "
                f"{counts['hidden']} oculta(s) (exigem visto), "
                f"{counts['duplicates']} repetida(s), {counts['reposts']} republicada(s)"
            )

            # 4. Pendentes = as de agora + as que falharam no envio anterior
            pending = get_pending_jobs(conn)
            retried = len(pending) - counts["to_send"]
            if retried > 0:
                print(f"🔁 {retried} vaga(s) de execuções anteriores ainda não entregue(s) — reenviando.")

            if pending:
                print("\n📋 VAGAS PARA ENVIAR:\n")
                for i, job in enumerate(pending, 1):
                    print(f"  {i}. [{job.get('score') or 0}] {job['title']}")
                    print(f"     🏢 {job['company']}  |  📍 {job['location']}")
                    print(f"     {job.get('eligibility_reason') or ''}")
                    print(f"     🔗 {job['job_url']}")
                    print()
            else:
                print("Nada de novo por enquanto. Tente novamente mais tarde.")

            # 5. Notifica sempre — com vagas ou sem
            print("📨  Enviando para o Telegram...\n")
            delivered = notify_jobs(pending, stats=scraper_stats, hidden_count=counts["hidden"])

            # 6. Marca só o que chegou de fato; o resto tenta de novo na próxima
            for url in delivered:
                mark_notified(conn, url)
            failed = len(pending) - len(delivered)
            if failed:
                print(f"⚠️  {failed} vaga(s) não entregue(s) — ficam pendentes para a próxima execução.")

        print("\n✅ Concluído!\n")

    except Exception as e:
        print(f"\n💥 Erro crítico: {e}")
        send_error_alert(str(e))
        raise


def run_radar():
    """
    Radar de ATS (radar.py). Mesmo caminho das vagas do JobSpy — dedup,
    elegibilidade, nota, banco —, mas só manda mensagem quando há o que enviar:
    ele roda de hora em hora.
    """
    print("\n" + "=" * 45)
    print("  📡 RADAR — sites de vagas das empresas")
    print("=" * 45 + "\n")

    try:
        with closing(init_db()) as conn:
            jobs, radar_stats = fetch_radar_jobs(is_known=lambda url: not is_new(conn, url))
            counts = process_new_jobs(conn, jobs)
            print(
                f"\n🆕 {len(jobs)} vaga(s) nova(s) no radar: {counts['to_send']} para enviar, "
                f"{counts['hidden']} oculta(s) (exigem visto), "
                f"{counts['duplicates']} repetida(s), {counts['reposts']} republicada(s)"
            )

            # Pendentes incluem as que falharam no envio anterior (de qualquer origem).
            pending = get_pending_jobs(conn)
            if pending:
                delivered = notify_jobs(
                    pending, stats=radar_stats, hidden_count=counts["hidden"], title="📡 Radar",
                )
                for url in delivered:
                    mark_notified(conn, url)
                failed = len(pending) - len(delivered)
                if failed:
                    print(f"⚠️  {failed} vaga(s) não entregue(s) — ficam pendentes para a próxima execução.")
            else:
                print("Nada novo no radar.")

        print("\n✅ Radar concluído!\n")

    except Exception as e:
        print(f"\n💥 Erro crítico no radar: {e}")
        send_error_alert(f"Radar: {e}")
        raise


if __name__ == "__main__":
    # python main.py         → sites de vagas (LinkedIn, Indeed, Glassdoor)
    # python main.py radar   → radar de ATS
    if sys.argv[1:] == ["radar"]:
        run_radar()
    else:
        run()
