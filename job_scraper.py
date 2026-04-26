# scrapers/job_scraper.py
# Usa a lib JobSpy que já lida com LinkedIn, Indeed e Glassdoor
#
# Glassdoor parou de funcionar? Rode: python glassdoor_manager.py

from jobspy import scrape_jobs
import pandas as pd

SEARCH_TERM = "Android"

KEYWORDS = [
    "Android",
    "android",
    "Automotive",
    "AOSP"
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
    ("Brazil",    "Brazil"),
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
    ("Romania",        "Romania"),
    ("Hungary",        "Hungary"),
    ("Slovakia",       "Slovakia"),
    ("Bulgaria",       "Bulgaria"),
    ("Croatia",        "Croatia"),
    ("Slovenia",       "Slovenia"),
    ("Serbia",         "Serbia"),
    ("Ukraine",        "Ukraine"),
    ("Lithuania",      "Lithuania"),
    ("Latvia",         "Latvia"),
    ("Estonia",        "Estonia"),
]

# Países com suporte ao Glassdoor (têm domínio próprio no JobSpy).
# O Glassdoor só é consultado para estes — usar glassdoor.com (USA) como base
# é o mais confiável pois o token CSRF é extraído desse domínio.
GLASSDOOR_REGIONS = [("United States", "USA")]


def is_relevant(title: str) -> bool:
    title_lower = title.lower()
    has_keyword = any(kw in title_lower for kw in KEYWORDS)
    is_blacklisted = any(term in title_lower for term in BLACKLIST_TITLES)
    return has_keyword and not is_blacklisted


def _scrape_and_collect(site_names, location, country_indeed, hours_old, stats, all_jobs, label=None):
    label = label or location
    print(f"🔍 Buscando: '{SEARCH_TERM}' em {label} ({', '.join(site_names)})...")
    stats["requests"] += 1
    try:
        jobs_df = scrape_jobs(
            site_name=site_names,
            search_term=SEARCH_TERM,
            location=location,
            results_wanted=20,
            hours_old=hours_old,
            country_indeed=country_indeed,
        )

        if jobs_df is None or jobs_df.empty:
            print(f"  ⚠️  Nenhuma vaga encontrada em {label}")
            return

        for _, row in jobs_df.iterrows():
            title = str(row.get("title", ""))
            if not is_relevant(title):
                continue

            all_jobs.append({
                "title":       title,
                "company":     str(row.get("company", "N/A")),
                "location":    str(row.get("location", "N/A")),
                "job_url":     str(row.get("job_url", "")),
                "source":      str(row.get("site", "N/A")),
                "date_posted": str(row.get("date_posted", "N/A")),
                "salary":      str(row.get("min_amount", "")) + " - " + str(row.get("max_amount", "")),
                "description": str(row.get("description", ""))[:500],
            })

    except Exception as e:
        stats["errors"] += 1
        print(f"  ❌ Erro ao buscar em {label}: {e}")


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
            ["glassdoor"], location, country_indeed, hours_old, stats, all_jobs,
            label=f"{location} (Glassdoor global)"
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
