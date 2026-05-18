# scheduler.py
# Roda o job hunter a cada 10 minutos, exibindo novas vagas encontradas

import schedule
import time
from main import run
from notifier import send_error_alert

INTERVALO_MINUTOS = 720

print(f"⏰ Agendador iniciado — verificando a cada {INTERVALO_MINUTOS} minutos")
print("   Pressione Ctrl+C para parar.\n")


def run_safe():
    """Wrapper que garante que o scheduler não morra silenciosamente."""
    try:
        run()
    except Exception as e:
        # run() já notificou via send_error_alert, mas logamos aqui também
        print(f"\n💥 Execução encerrou com erro: {e}")
        print("   Scheduler continua ativo para a próxima rodada.\n")


schedule.every(INTERVALO_MINUTOS).minutes.do(run_safe)

# Roda uma vez imediatamente ao iniciar
run_safe()

while True:
    schedule.run_pending()
    time.sleep(60)
