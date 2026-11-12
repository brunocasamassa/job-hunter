# 🤖 Job Hunter — Android Developer

Radar automático de vagas que busca no LinkedIn, Indeed e Glassdoor
e te notifica no Telegram quando aparecem vagas novas.

---

## 📁 Estrutura

```
job-hunter/
├── main.py               # Orquestra tudo (rode este)
├── scheduler.py          # Roda main.py a cada INTERVALO_MINUTOS
├── job_scraper.py        # Busca vagas com JobSpy + filtro de títulos
├── eligibility.py        # Você pode trabalhar na vaga? (país, visto, idioma)
├── dedupe.py             # Mesma vaga em sites diferentes / republicada
├── ranking.py            # Nota de 0 a 10 para ordenar o resumo
├── tracker.py            # Banco SQLite (histórico, pendentes)
├── notifier.py           # Envia o resumo no Telegram
├── jobspy_patches.py     # Workarounds para bugs do JobSpy (Glassdoor)
├── logger.py             # Logging detalhado do Glassdoor
├── glassdoor_manager.py  # Testa se o Glassdoor está respondendo
├── tests/                # Testes (pytest)
├── requirements.txt
└── requirements-dev.txt
```

---

## ⚙️ Instalação

### 1. Pré-requisitos
- Python 3.10+
- pip

### 2. Clone / copie a pasta e instale as dependências

```bash
cd job-hunter
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

### Passo 3 — Criar o arquivo `.env`
Na raiz do projeto, crie um arquivo `.env` (ele já está no `.gitignore`):

```
TELEGRAM_TOKEN=7123456789:AAF...
TELEGRAM_CHAT_ID=123456789
```

### Passo 4 — Iniciar o bot
No Telegram, busque seu bot pelo username e envie `/start`.

---

## ▶️ Como rodar

### Rodar uma vez agora
```bash
python main.py
```

### Rodar automaticamente (deixa o terminal aberto)
```bash
python scheduler.py
```

### Rodar em background (Linux/Mac)
```bash
nohup python scheduler.py > log.txt 2>&1 &
```

---

## ⚙️ Personalizar

### Termos de busca e países
Em `job_scraper.py`. Cada termo de `SEARCH_TERMS` repete todas as buscas
(mais termos = mais requests; o LinkedIn limita por IP).

```python
SEARCH_TERMS = ["Android"]

# (location, country_indeed, modo)
REGIONS = [
    ("Germany",       "Germany", ALL),     # todas as vagas
    ("United States", "USA",     REMOTE),  # só remotas (país exige visto)
]
```

- `ALL`: países onde você pode trabalhar — UE/EEE/Suíça (cidadania italiana),
  Brasil e Mercosul (residência facilitada para brasileiros).
- `REMOTE`: países que exigem visto; presencial lá seria descartado de qualquer jeito.
- Glassdoor só existe em alguns países: lista própria em `GLASSDOOR_REGIONS`.

### Elegibilidade e idiomas
`eligibility.py` classifica cada vaga:

| Resultado | Quando |
|---|---|
| ✅ Pode aplicar | País da UE/EEE/Suíça ou Brasil; ou remota aberta a LatAm/Brasil/qualquer lugar |
| ⚠️ Confira antes | Mercosul, oferece visto/relocação, sinais contraditórios ou sem descrição |
| ❌ Exige visto | Pede autorização/residência local ("must be authorized to work in the US", "no sponsorship"…) ou não diz que aceita LatAm |

As ❌ não são enviadas (só contadas no resumo). Para recebê-las também, em `main.py`:
`SHOW_INELIGIBLE = True`.

Vaga que exige idioma que você não fala ganha o aviso `🗣️ exige alemão`.
Ajuste em `eligibility.py`:
```python
SPOKEN_LANGUAGES = frozenset({"english", "portuguese"})
```

### Vagas repetidas e republicadas
A mesma empresa + título + país em dois sites vira uma vaga só (fica a versão
com link do site da empresa). Se reaparecer com outra URL em menos de
`REPOST_WINDOW_DAYS` (30, em `main.py`), não alerta de novo; depois disso,
alerta com `🔁 já vista em …` — às vezes é vaga fantasma.

### Palavras-chave e títulos indesejados
Em `job_scraper.py`. Maiúsculas/minúsculas não importam.
- `KEYWORDS` casa como trecho do título (`"android"` pega "Senior Android Engineer").
- `BLACKLIST_TITLES` casa como palavra inteira (`"ios"` pega "Android/iOS", mas não "Studios").

```python
KEYWORDS = ["Android", "Automotive"]
BLACKLIST_TITLES = ["react native", "flutter", "ios"]
```

### Detalhes das vagas do LinkedIn
A busca do LinkedIn não traz descrição nem o link de candidatura no site da
empresa. O `job_scraper.py` busca esses detalhes só das vagas **novas**
(1 request por vaga, com teto por execução):

```python
LINKEDIN_FETCH_DETAILS = True        # False desliga
LINKEDIN_DETAILS_MAX_PER_RUN = 60
```

### Intervalo do agendador
Em `scheduler.py`:
```python
INTERVALO_MINUTOS = 720   # 12 horas
```

### Janela da busca e histórico
Em `main.py`:
```python
HOURS_OLD = 24       # só vagas publicadas nas últimas 24h
HISTORY_DAYS = 180   # quanto tempo lembrar das vagas já vistas
```

---

## 📨 O que chega no Telegram

Um resumo por execução, maior nota primeiro (quebrado em várias mensagens se
for longo):

```
🔔 Job Hunter — 5 vaga(s)
⏰ 17:05 • 12/11/2026
🔍 Buscas: 41 | ✅ Erros: 0
🙈 1 oculta(s): exigem visto/residência

✅ Pode aplicar

1. ⭐8 Senior Android Automotive Engineer
🏢 ACME · 📍 Munich, BY, DE · INDEED
🇪🇺 UE/EEE/Suíça — sem visto · 🗣️ exige alemão · 💰 75,000 - 95,000 EUR/yearly
🔗 Ver vaga · 🎯 Aplicar no site da empresa

2. ⭐7 Senior Android Engineer
🏢 Gamma Inc · 📍 Remote · INDEED
🌎 Remoto aberto a LatAm/Brasil
🔗 Ver vaga

⚠️ Confira antes

3. ⭐5 Android Platform Engineer
🏢 Zeta Ltd · 📍 Remote, UK · INDEED
⚠️ Oferece visto/relocação
🔗 Ver vaga
```

Se alguma mensagem falhar (Telegram fora do ar, limite de envio), as vagas dela
ficam pendentes no banco e são reenviadas na próxima execução.

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

## 🧪 Testes

```bash
pip install -r requirements-dev.txt
pytest
```

Os testes não acessam a internet: LinkedIn, JobSpy e Telegram são simulados.

---

## ❓ Problemas comuns

| Problema | Solução |
|---|---|
| `ModuleNotFoundError: jobspy` | `pip install -r requirements.txt` |
| `KeyError: 'TELEGRAM_TOKEN'` | Crie o `.env` (Passo 3) |
| Telegram não recebe | Confirme token e chat_id; envie `/start` pro bot |
| Nenhuma vaga encontrada | Aumente `HOURS_OLD = 72` em `main.py` |
| LinkedIn bloqueou | JobSpy já rotaciona headers; tente novamente mais tarde |
| "Detalhes do LinkedIn: 0 ok, 3 falharam" | Limite por IP; ponha `LINKEDIN_FETCH_DETAILS = False` por um tempo |
