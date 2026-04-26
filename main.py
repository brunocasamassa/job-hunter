# main.py
# Orquestra scraping → filtragem → banco → notificação

# ---------------------------------------------------------------------------
# TODO — Glassdoor não está retornando vagas (erro 400 / "location not parsed")
#
# CAUSA RAIZ:
#   O token CSRF do Glassdoor expira periodicamente. O JobSpy tenta buscar um
#   token fresh a cada execução visitando glassdoor.com, mas o endpoint de
#   localização (findPopularLocationAjax.htm) rejeita com 400 quando o token
#   ou os cookies de sessão estão inválidos.
#
# O QUE JÁ FOI CORRIGIDO:
#   - "glassdoor" foi adicionado ao site_name em job_scraper.py
#   - O monkey-patch com token no formato errado (MD5 hex) foi removido
#   - Glassdoor agora roda só para "United States" (glassdoor.com),
#     evitando domínios regionais que causavam falhas adicionais
#
# O QUE FALTA RESOLVER — token CSRF expirado:
#   1. Abra glassdoor.com no browser
#   2. DevTools → aba Network → faça qualquer busca de vaga
#   3. Filtre por "findPopularLocation" ou "graph"
#   4. Em qualquer requisição, copie o header "gd-csrf-token"
#      O formato atual é hex simples: ex. e07f85946a6543c3a52ea48c4d8baa1d
#   5. Em job_scraper.py, adicione o bloco abaixo com o valor copiado:
#
#      import jobspy.glassdoor.constant as _gd_const
#      _gd_const.fallback_token = "SEU_TOKEN_AQUI"
#
#   6. Rode: python glassdoor_manager.py
#      → se retornar vagas, está funcionando
#      → se retornar 0, o token expirou de novo — repita os passos acima
#
# NOTA: o fallback embutido no JobSpy usa formato antigo (xxxxx:yyyyy:zzzzz)
#       que o Glassdoor não aceita mais. O formato atual é hex simples.
# ---------------------------------------------------------------------------

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
