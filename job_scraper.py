# job_scraper.py
# Usa a lib JobSpy que já lida com LinkedIn, Indeed e Glassdoor
#
# Glassdoor parou de funcionar? Rode: python glassdoor_manager.py

import random
import re
import time

import pandas as pd
import logger
import jobspy_patches  # noqa: F401
from jobspy.linkedin import LinkedIn
from jobspy.model import ScraperInput, Site

SEARCH_TERM = "Android"

# A busca do LinkedIn não traz descrição nem o link de candidatura no site da
# empresa. Buscamos esses detalhes só das vagas NOVAS, 1 request por vaga.
# O LinkedIn limita por IP: há teto por execução e parada automática depois de
# falhas seguidas. Se começar a bloquear, ponha False.
LINKEDIN_FETCH_DETAILS = True
LINKEDIN_DETAILS_MAX_PER_RUN = 60
LINKEDIN_DETAILS_DELAY_SECONDS = (2.0, 4.0)
LINKEDIN_DETAILS_MAX_CONSECUTIVE_FAILURES = 3

# Teto para a descrição guardada no banco.
DESCRIPTION_MAX_CHARS = 20_000

# KEYWORDS e BLACKLIST_TITLES não diferenciam maiúsculas/minúsculas.
# - KEYWORDS casam como trecho do título ("android" pega "Android Engineer").
# - BLACKLIST_TITLES casam como palavra inteira ("ios" pega "Android/iOS",
#   mas não "Studios").
KEYWORDS = [
    "Android",
    "android",
    "Automotive",
    "AOSP",
    "mobile"
]

BLACKLIST_TITLES = [
    "react native",
    "flutter",
    "ios only",
    "fullstack",
    "ios developer",
    "Backend developer",
    "ios",
    "Quality Assurance"

]

# (location, country_indeed) — location é usado pelo LinkedIn/Glassdoor,
# country_indeed restringe o domínio regional do Indeed.
REGIONS = [
    # América do Sul
    ("Brasil",    "Brazil"),
    ("Argentina", "Argentina"),
    ("Colombia",  "Colombia"),
    ("Chile",     "Chile"),
    # América do Norte
    ("United States", "USA"),
    ("Canada",        "Canada"),
    ("Mexico",        "Mexico"),
    # Europa
    ("United Kingdom", "UK"),
    ("Germany",        "Germany"),
    ("Netherlands",    "Netherlands"),
    ("Portugal",       "Portugal"),
    ("Spain",          "Spain"),
    ("France",         "France"),
    ("Sweden",         "Sweden"),
    ("Switzerland",    "Switzerland"),
    ("Ireland",        "Ireland"),
    ("Poland",         "Poland"),
    # Leste Europeu
    ("Czech Republic", "Czech Republic"),
    ("Hungary",        "Hungary"),
    ("Slovakia",       "Slovakia"),
    ("Bulgaria",       "Bulgaria"),
    ("Croatia",        "Croatia"),
    ("Lithuania",      "Lithuania"),
    ("Latvia",         "Latvia"),
    ("Estonia",        "Estonia"),
    # Ásia
    ("Thailand",       "Thailand"),
    ("Singapore",      "Singapore"),
    ("Indonesia",      "Indonesia"),
]

# Países com domínio Glassdoor próprio no enum do JobSpy.
# Demais países em REGIONS lançam `Glassdoor is not available for X` —
# por isso a lista do Glassdoor é separada da do LinkedIn/Indeed.
GLASSDOOR_REGIONS = [
    ("Brasil",         "Brazil"),
    ("Argentina",      "Argentina"),
    ("United States",  "USA"),
    ("Canada",         "Canada"),
    ("Mexico",         "Mexico"),
    ("United Kingdom", "UK"),
    ("Germany",        "Germany"),
    ("Netherlands",    "Netherlands"),
    ("Spain",          "Spain"),
    ("France",         "France"),
    ("Switzerland",    "Switzerland"),
    ("Ireland",        "Ireland"),
    ("Singapore",      "Singapore"),
]


def _compile_blacklist(terms: list[str]) -> re.Pattern:
    """Regex que casa qualquer termo da blacklist como palavra inteira."""
    normalized = sorted({t.strip().lower() for t in terms if t.strip()}, key=len, reverse=True)
    if not normalized:
        return re.compile(r"(?!)")  # blacklist vazia: nunca casa
    return re.compile(r"\b(?:" + "|".join(map(re.escape, normalized)) + r")\b")


_KEYWORDS_NORMALIZED = tuple({kw.strip().lower() for kw in KEYWORDS if kw.strip()})
_BLACKLIST_PATTERN = _compile_blacklist(BLACKLIST_TITLES)


def is_relevant(title: str) -> bool:
    """
    Incluir a mais é barato (você só vê uma vaga extra); excluir a mais custa
    uma vaga. Por isso keyword casa por trecho e blacklist por palavra inteira.
    """
    title_lower = title.lower()
    has_keyword = any(kw in title_lower for kw in _KEYWORDS_NORMALIZED)
    return has_keyword and _BLACKLIST_PATTERN.search(title_lower) is None


def _is_missing(value) -> bool:
    """None, NaN e NaT (o que o pandas devolve em campo vazio)."""
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):  # listas/arrays não são "vazio"
        return False


def _clean(value, default: str = "N/A") -> str:
    """Texto do campo, ou `default` se vier vazio (evita 'nan' no Telegram)."""
    if _is_missing(value):
        return default
    text = str(value).strip()
    return text or default


def _format_salary(row) -> str:
    """'50,000 - 70,000 EUR/yearly', ou '' quando a vaga não informa salário."""
    amounts = []
    for key in ("min_amount", "max_amount"):
        value = row.get(key)
        if _is_missing(value):
            continue
        try:
            amounts.append(f"{float(value):,.0f}")
        except (TypeError, ValueError):
            continue
    if not amounts:
        return ""

    text = " - ".join(amounts)
    currency = _clean(row.get("currency"), default="")
    interval = _clean(row.get("interval"), default="")
    if currency:
        text += f" {currency}"
    if interval:
        text += f"/{interval}"
    return text


def _scrape_and_collect(site_names, location, country_indeed, hours_old, stats, all_jobs, label=None):
    label = label or location
    print(f"\n🔍 Buscando: '{SEARCH_TERM}' em {label} ({', '.join(site_names)})...")
    stats["requests"] += 1
    try:
        jobs_df = logger.debug_scrape(
            site_names, SEARCH_TERM, location, country_indeed, hours_old
        )
        if jobs_df is None or jobs_df.empty:
            return

        kept = 0
        for _, row in jobs_df.iterrows():
            title = str(row.get("title", ""))
            if not is_relevant(title):
                continue
            kept += 1

            all_jobs.append({
                "title":       title,
                "company":     _clean(row.get("company")),
                "location":    _clean(row.get("location")),
                "job_url":     _clean(row.get("job_url"), default=""),
                "source":      _clean(row.get("site")),
                "date_posted": _clean(row.get("date_posted")),
                "salary":      _format_salary(row),
                "url_direct":  _clean(row.get("job_url_direct"), default=""),
                "description": _clean(row.get("description"), default="")[:DESCRIPTION_MAX_CHARS],
            })

        print(f"  ✅ {kept}/{len(jobs_df)} passaram no filtro de título")

    except Exception:
        stats["errors"] += 1


def fetch_jobs(hours_old: int = 24) -> tuple[list[dict], dict]:
    """
    Busca vagas nos últimos `hours_old` horas em múltiplas regiões.
    - LinkedIn + Indeed: todas as regiões em REGIONS
    - Glassdoor: apenas regiões em GLASSDOOR_REGIONS (usa glassdoor.com)
    Retorna (jobs, stats) onde stats = {"requests": int, "errors": int}.
    """
    all_jobs = []
    stats = {"requests": 0, "errors": 0}

    for location, country_indeed in REGIONS:
        _scrape_and_collect(
            ["indeed", "linkedin"], location, country_indeed, hours_old, stats, all_jobs
        )

    for location, country_indeed in GLASSDOOR_REGIONS:
        _scrape_and_collect(
            ["glassdoor"], location, country_indeed, hours_old, stats, all_jobs
        )

    # Remove duplicatas pelo link
    seen = set()
    unique_jobs = []
    for job in all_jobs:
        if job["job_url"] not in seen:
            seen.add(job["job_url"])
            unique_jobs.append(job)

    print(f"\n✅ Total de vagas únicas encontradas: {len(unique_jobs)}")
    return unique_jobs, stats


def _linkedin_job_id(job_url: str) -> str | None:
    match = re.search(r"/jobs/view/(\d+)", job_url or "")
    return match.group(1) if match else None


def enrich_linkedin_details(jobs: list[dict]) -> dict:
    """
    Completa `description` e `url_direct` das vagas do LinkedIn que vieram sem
    eles. Altera os dicts no lugar. Chame só com vagas novas: 1 request por vaga.
    Retorna {"fetched": n, "failed": n, "skipped": n}.
    """
    stats = {"fetched": 0, "failed": 0, "skipped": 0}
    targets = [
        job for job in jobs
        if job.get("source") == "linkedin" and not job.get("description")
    ]
    if not targets:
        return stats
    if not LINKEDIN_FETCH_DETAILS:
        stats["skipped"] = len(targets)
        return stats

    scraper = LinkedIn()
    # _get_job_details é interno do JobSpy 1.1.82 e lê o formato da descrição
    # de scraper_input — que só é preenchido dentro de scrape().
    scraper.scraper_input = ScraperInput(site_type=[Site.LINKEDIN])

    consecutive_failures = 0
    for position, job in enumerate(targets):
        attempts = stats["fetched"] + stats["failed"]
        if consecutive_failures >= LINKEDIN_DETAILS_MAX_CONSECUTIVE_FAILURES:
            print("  ⚠️  LinkedIn parou de devolver detalhes (provável limite por IP). Pulando o resto.")
            stats["skipped"] += len(targets) - position
            break
        if attempts >= LINKEDIN_DETAILS_MAX_PER_RUN:
            stats["skipped"] += len(targets) - position
            break

        job_id = _linkedin_job_id(job.get("job_url", ""))
        if job_id is None:
            stats["skipped"] += 1
            continue

        if attempts:
            time.sleep(random.uniform(*LINKEDIN_DETAILS_DELAY_SECONDS))
        details = scraper._get_job_details(job_id)
        if not details:  # o JobSpy devolve {} em qualquer falha, inclusive 429
            stats["failed"] += 1
            consecutive_failures += 1
            continue

        consecutive_failures = 0
        stats["fetched"] += 1
        if details.get("description"):
            job["description"] = str(details["description"])[:DESCRIPTION_MAX_CHARS]
        if details.get("job_url_direct"):
            job["url_direct"] = str(details["job_url_direct"])

    print(
        f"🔎 Detalhes do LinkedIn: {stats['fetched']} ok, "
        f"{stats['failed']} falharam, {stats['skipped']} pulados"
    )
    return stats
