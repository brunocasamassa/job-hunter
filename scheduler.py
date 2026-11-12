# scheduler.py
# Roda o job hunter (LinkedIn, Indeed, Glassdoor) a cada INTERVALO_MINUTOS e o
# radar de ATS (radar.py) a cada RADAR_INTERVALO_MINUTOS.

import schedule
import time
from main import run, run_radar

INTERVALO_MINUTOS = 720

# O radar só lê as APIs públicas das empresas em radar.BOARDS, então pode rodar
# bem mais vezes. 0 desliga.
RADAR_INTERVALO_MINUTOS = 60

print(f"⏰ Agendador iniciado — sites de vagas a cada {INTERVALO_MINUTOS} minutos", end="")
print(f", radar a cada {RADAR_INTERVALO_MINUTOS} minutos" if RADAR_INTERVALO_MINUTOS else ", radar desligado")
print("   Pressione Ctrl+C para parar.\n")


def _safe(job, name):
    """Wrapper que garante que o scheduler não morra silenciosamente."""
    def wrapped():
        try:
            job()
        except Exception as e:
            # a função já notificou via send_error_alert, mas logamos aqui também
            print(f"\n💥 {name} encerrou com erro: {e}")
            print("   Scheduler continua ativo para a próxima rodada.\n")
    return wrapped


run_safe = _safe(run, "Execução")
run_radar_safe = _safe(run_radar, "Radar")

schedule.every(INTERVALO_MINUTOS).minutes.do(run_safe)
if RADAR_INTERVALO_MINUTOS:
    schedule.every(RADAR_INTERVALO_MINUTOS).minutes.do(run_radar_safe)

# Roda uma vez imediatamente ao iniciar
run_safe()
if RADAR_INTERVALO_MINUTOS:
    run_radar_safe()

while True:
    schedule.run_pending()
    time.sleep(60)
