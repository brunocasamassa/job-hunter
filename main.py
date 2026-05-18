# main.py
# Orquestra scraping → filtragem → banco → notificação


from job_scraper import fetch_jobs
from tracker import init_db, is_new, save_job, mark_notified, purge_old_jobs
from notifier import notify_jobs, send_error_alert


def run():
    print("\n" + "=" * 45)
    print("  🤖 JOB HUNTER — Android Developer")
    print("=" * 45 + "\n")

    try:
        # 1. Inicializa banco e limpa registros antigos
        conn = init_db()
        deleted = purge_old_jobs(conn, days=10)
        if deleted:
            print(f"🗑️  {deleted} vaga(s) antigas removidas do cache.")

        # 2. Busca vagas (últimas 24h)
        jobs, scraper_stats = fetch_jobs(hours_old=24)

        # 3. Filtra só as novas (não vistas antes)
        new_jobs = []
        for job in jobs:
            if is_new(conn, job["job_url"]):
                save_job(conn, job)
                new_jobs.append(job)

        print(f"\n🆕 Vagas novas (não vistas antes): {len(new_jobs)}")

        if new_jobs:
            # 4. Exibe no terminal
            print("\n📋 VAGAS ENCONTRADAS:\n")
            for i, job in enumerate(new_jobs, 1):
                print(f"  {i}. {job['title']}")
                print(f"     🏢 {job['company']}")
                print(f"     📍 {job['location']}  |  📅 {job['date_posted']}")
                print(f"     🔗 {job['job_url']}")
                print()

            # 5. Marca como notificadas
            for job in new_jobs:
                mark_notified(conn, job["job_url"])
        else:
            print("Nada de novo por enquanto. Tente novamente mais tarde.")

        conn.close()

        # 6. Notifica sempre — com vagas ou sem
        print("📨  Enviando para o Telegram...\n")
        notify_jobs(new_jobs, stats=scraper_stats)

        print("\n✅ Concluído!\n")

    except Exception as e:
        print(f"\n💥 Erro crítico: {e}")
        send_error_alert(str(e))
        raise


if __name__ == "__main__":
    run()
