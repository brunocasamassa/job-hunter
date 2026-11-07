import os

# notifier.py lê as credenciais ao ser importado. Valores fixos de teste
# (sobrescrevem um .env real, que o load_dotenv não força por cima).
os.environ["TELEGRAM_TOKEN"] = "123456:TEST-TOKEN"
os.environ["TELEGRAM_CHAT_ID"] = "42"
