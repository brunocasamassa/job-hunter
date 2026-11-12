# main.py
# Orquestra scraping → filtragem → banco → notificação

from contextlib import closing

from job_scraper import fetch_jobs, enrich_linkedin_details
from tracker import init_db, is_new, save_job, get_pending_jobs, mark_notified, purge_old_jobs
from notifier import notify_jobs, send_error_alert

# Quanto tempo lembrar das vagas já vistas. Com 10 dias, uma vaga republicada
# com a mesma URL voltava como "nova"; o banco é pequeno, dá para guardar mais.
HISTORY_DAYS = 180

# Janela da busca: só vagas publicadas nas últimas N horas.
HOURS_OLD = 24


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

            # 3. Separa as novas (não vistas antes) e completa as do LinkedIn
            #    com descrição + link do site da empresa antes de salvar
            new_jobs = [job for job in jobs if is_new(conn, job["job_url"])]
            print(f"\n🆕 Vagas novas (não vistas antes): {len(new_jobs)}")
            enrich_linkedin_details(new_jobs)
            for job in new_jobs:
                save_job(conn, job)

            # 4. Pendentes = novas + as que falharam no envio anterior
            pending = get_pending_jobs(conn)
            retried = len(pending) - len(new_jobs)
            if retried > 0:
                print(f"🔁 {retried} vaga(s) de execuções anteriores ainda não entregue(s) — reenviando.")

            if pending:
                print("\n📋 VAGAS PARA ENVIAR:\n")
                for i, job in enumerate(pending, 1):
                    print(f"  {i}. {job['title']}")
                    print(f"     🏢 {job['company']}")
                    print(f"     📍 {job['location']}  |  📅 {job['date_posted']}")
                    print(f"     🔗 {job['job_url']}")
                    print()
            else:
                print("Nada de novo por enquanto. Tente novamente mais tarde.")

            # 5. Notifica sempre — com vagas ou sem
            print("📨  Enviando para o Telegram...\n")
            delivered = notify_jobs(pending, stats=scraper_stats)

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


if __name__ == "__main__":
    run()
