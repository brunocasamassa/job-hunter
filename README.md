# 🤖 Job Hunter — Android Developer

Radar automático de vagas que busca no LinkedIn, Indeed e Glassdoor — e direto
nos sites de vagas de empresas escolhidas (Greenhouse, Lever, Ashby) — e te
notifica no Telegram quando aparecem vagas novas.

---

## 📁 Estrutura

```
job-hunter/
├── main.py               # Orquestra tudo (rode este)
├── scheduler.py          # Agenda os sites de vagas e o radar
├── job_scraper.py        # Busca vagas com JobSpy + filtro de títulos
├── radar.py              # Radar de ATS: empresas escolhidas e filtros
├── ats.py                # APIs públicas do Greenhouse, Lever e Ashby
├── locations.py          # País da vaga a partir do local ("Kraków", "Remote - EU")
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
python main.py         # LinkedIn, Indeed e Glassdoor
python main.py radar   # radar de ATS
```

### Rodar automaticamente (deixa o terminal aberto)
```bash
python scheduler.py   # sites de vagas a cada 12 h, radar a cada 1 h; os dois rodam já na largada
```

### Rodar em background (Linux/Mac)
```bash
nohup python scheduler.py > log.txt 2>&1 &
```

---

## 📡 Radar de ATS

Lê direto as vagas abertas de empresas escolhidas, nas APIs públicas de vagas
do Greenhouse, do Lever e do Ashby (feitas para as empresas montarem suas
páginas de carreira; não precisam de chave). A vaga chega em até uma hora
depois de publicada, e o link leva à candidatura no sistema da própria empresa,
sem passar pelo LinkedIn.

- Roda a cada `RADAR_INTERVALO_MINUTOS` (60, em `scheduler.py`; 0 desliga).
- Só manda mensagem quando há vaga nova. O resumo vem com o título `📡 Radar`.
- Na primeira vez chegam todas as vagas abertas que passarem nos filtros;
  depois, só as novas.
- Passa pelo mesmo caminho das outras vagas: filtro de título, elegibilidade,
  nota e dedup. Se a vaga já chegou pelo LinkedIn (mesma empresa, título e
  país), não chega de novo.
- Como o radar recebe **todas** as vagas da empresa, a vaga também precisa citar
  Android, AAOS ou AOSP no título ou na descrição (`RADAR_REQUIRED_TERMS`).
- A mesma vaga publicada em vários países (o Lever faz uma por local) vira um
  alerta só, com os locais juntos.
- Cada vaga mostra há quanto tempo foi publicada (`📅 há 3 dias`). Algumas
  empresas deixam a mesma vaga aberta por meses; para esconder as antigas, use
  `RADAR_MAX_AGE_DAYS` em `radar.py`.

### Incluir uma empresa
Abra a página de vagas dela e veja o endereço:

| Endereço da vaga | Em `radar.BOARDS` |
|---|---|
| `boards.greenhouse.io/<token>` ou `job-boards.greenhouse.io/<token>` | `Board("Empresa", GREENHOUSE, "<token>")` |
| `job-boards.eu.greenhouse.io/<token>` | `Board("Empresa", GREENHOUSE_EU, "<token>")` |
| `jobs.lever.co/<token>` | `Board("Empresa", LEVER, "<token>")` |
| `jobs.eu.lever.co/<token>` | `Board("Empresa", LEVER_EU, "<token>")` |
| `jobs.ashbyhq.com/<token>` | `Board("Empresa", ASHBY, "<token>")` |

- No Greenhouse e no Lever, se errar a região (EU ou não), o radar tenta a
  outra e avisa no log.
- No Lever dá para filtrar pelo time e baixar menos dados:
  `Board("Finom", LEVER_EU, "pnlfin", {"team": "Android"})`.
- Empresas em outros sistemas (Workday, Teamtailor, SmartRecruiters ou site
  próprio) ainda não entram: o radar só lê os três acima.

---

## ⚙️ Personalizar

### Termos de busca e países
Em `job_scraper.py`. Cada termo de `SEARCH_TERMS` repete todas as buscas
(mais termos = mais requests; o LinkedIn limita por IP).

```python
SEARCH_TERMS = ["Android"]

# (location, country_indeed, modo)
REGIONS = [
    ("Germany", "Germany", ALL),           # todas as vagas
    ("Romania", "Romania", ALL),
    # ("United States", "USA", REMOTE),    # só remotas (país exige visto)
]
```

- `ALL`: países onde você pode trabalhar — UE/EEE/Suíça (cidadania italiana),
  Brasil e Mercosul (residência facilitada para brasileiros).
- `REMOTE`: países que exigem visto; presencial lá seria descartado de qualquer
  jeito. Nenhum na lista hoje.
- A lista atual só tem países onde você pode trabalhar. Os comentários dizem
  quais empresas a pesquisa de nov/2026 achou contratando Android/Android Automotive.
- A ordem importa: se o LinkedIn bloquear no meio da execução, os últimos
  países ficam sem resultado.
- Glassdoor só existe em alguns países: lista própria em `GLASSDOOR_REGIONS`.
- Os testes conferem se cada país existe no JobSpy (e no Glassdoor, na lista
  dele) e se o modo `ALL` só aparece em país onde você pode trabalhar.

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
- `JUNIOR_TITLES` (júnior, estágio, intern, Werkstudent…) também casa como
  palavra inteira, mas só derruba a vaga se o título não tiver nível sênior
  (`SENIOR_TITLES`): "Junior/Regular/Senior Android Developer" continua.

```python
KEYWORDS = ["Android", "Automotive", "AAOS", "AOSP"]
BLACKLIST_TITLES = ["react native", "flutter", "ios", "full stack"]
JUNIOR_TITLES = ["junior", "jr", "intern", "trainee", "estágio"]
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
INTERVALO_MINUTOS = 720        # sites de vagas: 12 horas
RADAR_INTERVALO_MINUTOS = 60   # radar de ATS: 1 hora (0 desliga)
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
for longo). O do radar tem o título `📡 Radar`:

```
🔔 Job Hunter — 5 vaga(s)
⏰ 17:05 • 12/11/2026
🔍 Buscas: 34 | ✅ Erros: 0
🙈 1 oculta(s): exigem visto/residência

✅ Pode aplicar

1. ⭐8 Senior Android Automotive Engineer
🏢 ACME · 📍 Munich, BY, DE · INDEED
🇪🇺 UE/EEE/Suíça — sem visto · 📅 hoje · 🗣️ exige alemão · 💰 75,000 - 95,000 EUR/yearly
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

Os testes não acessam a internet: LinkedIn, JobSpy, as APIs dos ATS e o
Telegram são simulados.

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
| Radar: `❌ Empresa (...): 404` | Token errado ou a empresa trocou de sistema; confira o endereço da página de vagas |
| Radar: `o board está em ...` | Ajuste a região (`GREENHOUSE_EU`, `LEVER_EU`...) em `radar.BOARDS` |
