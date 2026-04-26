# 🤖 Job Hunter — Android Developer

Radar automático de vagas que busca no LinkedIn, Indeed e Glassdoor
e te notifica no Telegram quando aparecem vagas novas.

---

## 📁 Estrutura

```
job_hunter/
├── scrapers/
│   └── job_scraper.py   # Busca vagas com JobSpy
├── tracker.py           # Banco SQLite (evita duplicatas)
├── notifier.py          # Envia alertas no Telegram
├── main.py              # Orquestra tudo (rode este)
├── scheduler.py         # Roda automaticamente todo dia
├── requirements.txt
└── README.md
```

---

## ⚙️ Instalação

### 1. Pré-requisitos
- Python 3.10+
- pip

### 2. Clone / copie a pasta e instale as dependências

```bash
cd job_hunter
pip install -r requirements.txt
```

---

## 🔑 Configurar o Telegram (5 minutos)

### Passo 1 — Criar o bot
1. Abra o Telegram e busque **@BotFather**
2. Envie `/newbot`
3. Escolha um nome (ex: `Meu Job Hunter`)
4. Escolha um username (ex: `meu_job_hunter_bot`)
5. Copie o **token** que ele te mandar (ex: `7123456789:AAF...`)

### Passo 2 — Pegar seu Chat ID
1. Busque **@userinfobot** no Telegram
2. Envie `/start`
3. Ele te responde com seu **Id** (ex: `123456789`)

### Passo 3 — Colocar no código
Abra `notifier.py` e preencha:

```python
TELEGRAM_TOKEN   = "7123456789:AAF..."   # token do BotFather
TELEGRAM_CHAT_ID = "123456789"           # seu Id do userinfobot
```

### Passo 4 — Iniciar o bot
No Telegram, busque seu bot pelo username e envie `/start`.

---

## ▶️ Como rodar

### Rodar uma vez agora
```bash
python main.py
```

### Rodar todo dia automaticamente (deixa o terminal aberto)
```bash
python scheduler.py
```

### Rodar em background (Linux/Mac)
```bash
nohup python scheduler.py > log.txt 2>&1 &
```

---

## ⚙️ Personalizar

### Mudar palavras-chave de busca
Em `scrapers/job_scraper.py`:
```python
KEYWORDS = [
    "Android Developer",
    "Desenvolvedor Android",
    "Mobile Engineer Kotlin",
    # adicione mais aqui
]
```

### Filtrar títulos indesejados
```python
BLACKLIST_TITLES = [
    "react native",
    "flutter",
    "ios only",
    # adicione mais aqui
]
```

### Mudar horário do agendador
Em `scheduler.py`:
```python
HORARIO = "09:00"   # qualquer horário HH:MM
```

### Buscar vagas mais antigas
Em `main.py`, na chamada `fetch_jobs`:
```python
jobs = fetch_jobs(hours_old=48)   # últimas 48h
```

---

## 📨 O que chega no Telegram

```
🔔 Job Hunter — 3 vaga(s) nova(s)!

🤖 Vaga 1/3 — LINKEDIN
━━━━━━━━━━━━━━━━
📱 Android Developer Sênior
🏢 Nubank
📍 São Paulo, SP • Remoto
📅 2026-03-31
🔗 Ver vaga  ← link clicável
```

---

## 🗃️ Consultar vagas salvas

Abra o banco SQLite com qualquer client (ex: DB Browser for SQLite):
```
jobs.db
```

Ou via Python:
```python
from tracker import init_db, get_all_jobs
conn = init_db()
jobs = get_all_jobs(conn)
for j in jobs:
    print(j["title"], j["company"])
```

---

## ❓ Problemas comuns

| Problema | Solução |
|---|---|
| `ModuleNotFoundError: jobspy` | `pip install -r requirements.txt` |
| Telegram não recebe | Confirme token e chat_id; envie `/start` pro bot |
| Nenhuma vaga encontrada | Aumente `hours_old=72` em `main.py` |
| LinkedIn bloqueou | JobSpy já rotaciona headers; tente novamente em 10min |
