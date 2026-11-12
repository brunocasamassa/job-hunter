# radar.py
# Radar de ATS: lê direto os sites de vagas de empresas escolhidas
# (Greenhouse, Lever e Ashby), sem passar por LinkedIn, Indeed ou Glassdoor.
# Vaga que aparece aqui está no ar há menos de uma hora (o radar roda de hora
# em hora), e a candidatura vai direto para o sistema da empresa.
#
# Para incluir uma empresa, abra a página de vagas dela e veja o endereço:
#   (job-)boards.greenhouse.io/<token>   → GREENHOUSE
#   job-boards.eu.greenhouse.io/<token>  → GREENHOUSE_EU
#   jobs.lever.co/<token>                → LEVER
#   jobs.eu.lever.co/<token>             → LEVER_EU
#   jobs.ashbyhq.com/<token>             → ASHBY
# Se errar a região do Greenhouse/Lever, o radar tenta a outra e avisa no log.

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

import requests

import ats
from ats import ASHBY, GREENHOUSE, GREENHOUSE_EU, LEVER, LEVER_EU, Board
from dedupe import normalize_title
from eligibility import EUROPE
from job_scraper import is_relevant
from locations import infer_country, mentions_remote_europe

# Vaga publicada há mais dias que isso não alerta (None = sem limite). Só pesa
# na primeira rodada e quando você inclui uma empresa: depois, o que aparece
# acabou de sair. Sem limite porque algumas empresas deixam a mesma vaga aberta
# por meses (a de Android da Monzo em Barcelona é de out/2025); a data aparece
# no resumo para você decidir.
RADAR_MAX_AGE_DAYS = None

# Locais mostrados por vaga. O Lever publica a mesma vaga uma vez por país.
RADAR_MAX_PLACES = 6

# A vaga precisa citar um destes termos (palavra inteira) no título ou na
# descrição. Nos sites de vagas o termo de busca "Android" faz esse papel; o
# radar recebe todas as vagas da empresa, e "Automotive Sales Manager" passaria
# no filtro de título.
RADAR_REQUIRED_TERMS = ["Android", "AAOS", "AOSP"]

# Pausa entre empresas, para não sobrecarregar as APIs.
RADAR_DELAY_SECONDS = 1.0

# Empresas que contratam Android/Android Automotive onde você pode trabalhar
# (pesquisa de nov/2026). Tokens conferidos na API, menos os do Greenhouse UE,
# que não deu para testar daqui.
BOARDS = [
    # Automotivo e Android Automotive (AAOS)
    Board("TomTom", LEVER_EU, "tomtom"),                     # Amsterdã, Eindhoven
    Board("Paradox Cat", GREENHOUSE_EU, "paradoxcatgmbh"),   # Munique, Bucareste, remoto na Romênia
    Board("Applied Intuition", ASHBY, "applied"),            # Vehicle OS; Munique, Stuttgart, Estocolmo
    Board("Rivian and Volkswagen Group Technologies", ASHBY, "rivianvw.tech"),  # Berlim
    Board("Mapbox", ASHBY, "Mapbox"),                        # navegação automotiva; Helsinque
    Board("AscentCore", LEVER_EU, "ascentcore"),             # infotainment; Cluj, Timișoara, Iași
    Board("NavVis", GREENHOUSE_EU, "navvis"),                # Munique
    Board("AutoScout24", GREENHOUSE, "autoscout24"),         # Berlim, Munique
    Board("Adyen", GREENHOUSE, "adyen"),                     # AOSP em terminais; Amsterdã, Madri
    # Produtos com time Android na UE
    Board("Monzo", GREENHOUSE, "monzo"),                     # Barcelona
    Board("Wolt", GREENHOUSE, "wolt"),                       # Helsinque, Berlim, Estocolmo, Tallinn
    Board("Spotify", LEVER, "spotify", {"department": "Engineering"}),  # Estocolmo
    Board("Qonto", LEVER, "qonto", {"team": "Mobile - Android"}),       # remoto: Paris, Milão, Berlim, Barcelona, Lisboa
    Board("Finom", LEVER_EU, "pnlfin", {"team": "Android"}),            # remoto em vários países da UE
    Board("ElevenLabs", ASHBY, "elevenlabs"),                # remoto na Europa
    Board("AlphaSense", GREENHOUSE, "alphasense"),           # Helsinque
    Board("FREE NOW", GREENHOUSE, "freenow"),                # Hamburgo, Berlim, Barcelona, remoto na UE
    Board("Blacklane", GREENHOUSE, "blacklane"),             # Berlim, Barcelona, Madri
    Board("Bitpanda", GREENHOUSE, "bitpanda"),               # Viena, Barcelona, Berlim, Bucareste
    Board("Cabify", GREENHOUSE, "cabify"),                   # Madri ou remoto
    Board("Dashlane", GREENHOUSE, "dashlane"),               # remoto na Europa, Lisboa, Paris
    Board("LastPass", GREENHOUSE, "lastpass"),               # remoto em Portugal
    Board("Urban Sports Club", GREENHOUSE, "urbansportsclub"),  # Barcelona, Madri, Valência
    Board("Tripadvisor", GREENHOUSE, "tripadvisor"),         # Cracóvia
    Board("Customer.io", GREENHOUSE, "customerio"),          # remoto EMEA
    Board("Planner5D", LEVER, "planner5d"),                  # Varsóvia, Amsterdã, Barcelona
    Board("Numan", LEVER_EU, "numan"),                       # remoto na Romênia
    Board("voize", ASHBY, "voize"),                          # Berlim, Polônia
    Board("ARQ", ASHBY, "arq"),                              # Cracóvia (remoto)
    Board("Pragmatike", ASHBY, "pragmatike"),                # recrutadora; remoto EMEA
    # Remoto para a América Latina
    Board("Oowlish", LEVER, "oowlish"),                      # remoto Brasil/LatAm
]

_REQUIRED_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in RADAR_REQUIRED_TERMS) + r")\b",
    re.IGNORECASE,
)

# Vagas que passaram no título mas não citam Android. Ficam só na memória:
# assim o Greenhouse não busca a descrição delas de novo a cada rodada.
_skipped_urls: set[str] = set()


def _too_old(job: dict, now: datetime) -> bool:
    published = job.get("_published_at")
    if RADAR_MAX_AGE_DAYS is None or published is None:
        return False
    return now - published > timedelta(days=RADAR_MAX_AGE_DAYS)


def _mentions_required_term(job: dict) -> bool:
    return bool(_REQUIRED_PATTERN.search(job["title"]) or _REQUIRED_PATTERN.search(job["description"]))


def _merge_same_title(jobs: list[dict]) -> list[dict]:
    """
    A mesma vaga em vários países (o Lever publica uma por local) vira um
    alerta só: todas ganham a lista de locais e o mesmo país — o melhor para
    você —, e o dedup do main.py guarda a primeira e marca as outras como
    repetidas. A primeira é a do país escolhido, para o link abrir a vaga certa.
    """
    groups: dict[str, list[dict]] = {}
    for job in jobs:
        groups.setdefault(normalize_title(job["title"]), []).append(job)

    merged = []
    for group in groups.values():
        if len(group) > 1:
            places = list(dict.fromkeys(
                place for job in group for place in job["location"].split(" / ") if place != "N/A"
            ))
            country = infer_country(places) or group[0]["country"]
            shown = " / ".join(places[:RADAR_MAX_PLACES]) + (" / …" if len(places) > RADAR_MAX_PLACES else "")
            group.sort(key=lambda job: job["country"] != country)
            for job in group:
                job["location"] = shown or job["location"]
                job["country"] = country
        merged.extend(group)
    return merged


def fetch_radar_jobs(is_known: Callable[[str], bool], session=None,
                     now: datetime | None = None) -> tuple[list[dict], dict]:
    """
    Vagas novas dos BOARDS que passam nos filtros de título, termo obrigatório
    e idade. `is_known(url)` diz se a vaga já está no banco (aí nem busca a
    descrição). Retorna (vagas, {"requests": n, "errors": n}).
    """
    session = session or requests.Session()
    now = now or datetime.now(timezone.utc)
    stats = {"requests": 0, "errors": 0}
    found = []

    for position, board in enumerate(BOARDS):
        if position:
            time.sleep(RADAR_DELAY_SECONDS)
        stats["requests"] += 1
        try:
            listed = ats.list_jobs(board, session)
        except (requests.RequestException, ValueError) as error:
            stats["errors"] += 1
            print(f"  ❌ {board.company} ({board.ats}/{board.token}): {error}")
            continue

        kept = []
        for job in listed:
            url = job["job_url"]
            if url in _skipped_urls or not is_relevant(job["title"]) or is_known(url):
                continue
            if _too_old(job, now):
                continue
            if "_detail_url" in job:
                stats["requests"] += 1
                try:
                    ats.complete_job(job, session)
                except (requests.RequestException, ValueError) as error:
                    stats["errors"] += 1
                    print(f"  ❌ {board.company}: detalhes de '{job['title']}': {error}")
                    continue
            if not _mentions_required_term(job):
                _skipped_urls.add(url)
                continue
            if not job["country"] and mentions_remote_europe(job["description"]):
                job["country"] = EUROPE
            job.pop("_published_at", None)
            kept.append(job)
        found.extend(_merge_same_title(kept))
        print(f"📡 {board.company}: {len(kept)} nova(s) de {len(listed)} vaga(s)")

    return found, stats
