# ats.py
# Lê as APIs públicas de vagas do Greenhouse, do Lever e do Ashby (as mesmas
# que as páginas de carreira das empresas usam; não precisam de chave) e
# devolve as vagas no mesmo formato do job_scraper.
#
# Chaves que começam com "_" são internas do radar e não vão para o banco:
#   _published_at  datetime da publicação (ou None)
#   _detail_url    Greenhouse: a lista vem sem descrição; complete_job() busca

import html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser

import requests

from job_scraper import DESCRIPTION_MAX_CHARS
from locations import infer_country

GREENHOUSE = "greenhouse"
GREENHOUSE_EU = "greenhouse_eu"
LEVER = "lever"
LEVER_EU = "lever_eu"
ASHBY = "ashby"

_HOSTS = {
    GREENHOUSE: "https://boards-api.greenhouse.io",
    GREENHOUSE_EU: "https://boards-api.eu.greenhouse.io",
    LEVER: "https://api.lever.co",
    LEVER_EU: "https://api.eu.lever.co",
    ASHBY: "https://api.ashbyhq.com",
}
# Greenhouse e Lever têm uma instância na UE, e o token não diz qual é a dele.
# Se a região configurada responder 404, tenta a outra.
_OTHER_REGION = {
    GREENHOUSE: GREENHOUSE_EU, GREENHOUSE_EU: GREENHOUSE,
    LEVER: LEVER_EU, LEVER_EU: LEVER,
}
_SOURCE = {
    GREENHOUSE: "greenhouse", GREENHOUSE_EU: "greenhouse",
    LEVER: "lever", LEVER_EU: "lever",
    ASHBY: "ashby",
}

TIMEOUT_SECONDS = 20
_HEADERS = {"User-Agent": "job-hunter/1.0 (radar de vagas pessoal)"}


@dataclass
class Board:
    """Um site de vagas de uma empresa num ATS."""
    company: str
    ats: str                                    # GREENHOUSE, LEVER_EU, ASHBY...
    token: str                                  # o nome do board na URL
    params: dict = field(default_factory=dict)  # filtros do Lever, ex.: {"team": "Android"}


# ── Texto ────────────────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    _BLOCKS = {"p", "div", "br", "li", "ul", "ol", "tr", "section",
               "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(markup: str) -> str:
    """HTML → texto simples, uma linha por bloco (parágrafo, item de lista...)."""
    parser = _TextExtractor()
    parser.feed(markup or "")
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse_iso(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _from_epoch_ms(value) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _unique(values) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


# ── HTTP ─────────────────────────────────────────────────────────────────────

def _get_json(session, url: str, params: dict | None = None):
    response = session.get(url, params=params, timeout=TIMEOUT_SECONDS, headers=_HEADERS)
    response.raise_for_status()
    return response.json()


def _get_json_with_region_fallback(session, board: Board, path: str, params: dict):
    """Retorna (dados, host que respondeu)."""
    host = _HOSTS[board.ats]
    try:
        return _get_json(session, host + path, params), host
    except requests.HTTPError as error:
        other = _OTHER_REGION.get(board.ats)
        status = error.response.status_code if error.response is not None else None
        if other is None or status != 404:
            raise
    host = _HOSTS[other]
    data = _get_json(session, host + path, params)
    print(f"  ℹ️  {board.company}: o board está em {other}, não em {board.ats} — ajuste em radar.BOARDS")
    return data, host


def _job(board: Board, *, title: str, url: str, places: list[str], country: str,
         is_remote: bool, published: datetime | None, description: str = "",
         url_direct: str = "", salary: str = "") -> dict:
    return {
        "title": title,
        "company": board.company,
        "location": " / ".join(places) or "N/A",
        "job_url": url,
        "source": _SOURCE[board.ats],
        "date_posted": published.date().isoformat() if published else "N/A",
        "salary": salary,
        "url_direct": url_direct,
        "description": description[:DESCRIPTION_MAX_CHARS],
        "country": country,
        "is_remote": is_remote,
        "_published_at": published,
    }


# ── Greenhouse ───────────────────────────────────────────────────────────────

def _location_name(value) -> str:
    if isinstance(value, dict):
        return _text(value.get("name"))
    return _text(value)


def _greenhouse_jobs(board: Board, session) -> list[dict]:
    # Sem content=true: a lista com descrições de uma empresa grande passa de
    # alguns MB. A descrição vem depois, só das vagas novas (complete_job).
    data, host = _get_json_with_region_fallback(session, board, f"/v1/boards/{board.token}/jobs", {})
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ValueError("resposta inesperada do Greenhouse")

    jobs = []
    for item in data["jobs"]:
        if not isinstance(item, dict):
            continue
        title, url = _text(item.get("title")), _text(item.get("absolute_url"))
        if not title or not url:
            continue
        location = _location_name(item.get("location"))
        job = _job(
            board, title=title, url=url, places=_unique([location]),
            country=infer_country([location]),
            is_remote="remote" in location.lower(),
            published=_parse_iso(item.get("first_published")) or _parse_iso(item.get("updated_at")),
        )
        job["_detail_url"] = f"{host}/v1/boards/{board.token}/jobs/{item.get('id')}"
        jobs.append(job)
    return jobs


def complete_job(job: dict, session) -> None:
    """Busca a descrição (e os escritórios) de uma vaga do Greenhouse. Nos outros ATS não faz nada."""
    url = job.pop("_detail_url", None)
    if not url:
        return
    data = _get_json(session, url)
    if not isinstance(data, dict):
        raise ValueError("resposta inesperada do Greenhouse")
    # O Greenhouse devolve o HTML da descrição escapado em entidades (&lt;p&gt;).
    job["description"] = html_to_text(html.unescape(_text(data.get("content"))))[:DESCRIPTION_MAX_CHARS]
    offices = [office for office in data.get("offices") or [] if isinstance(office, dict)]
    office_places = [_text(office.get("location")) or _text(office.get("name")) for office in offices]
    job["country"] = infer_country([job["location"], *office_places]) or job["country"]


# ── Lever ────────────────────────────────────────────────────────────────────

def _lever_salary(salary_range) -> str:
    if not isinstance(salary_range, dict):
        return ""
    amounts = [f"{salary_range[key]:,.0f}" for key in ("min", "max")
               if isinstance(salary_range.get(key), (int, float))]
    if not amounts:
        return ""
    text = " - ".join(amounts)
    currency = _text(salary_range.get("currency"))
    # "per-year-salary" → "year"
    interval = _text(salary_range.get("interval")).removeprefix("per-").split("-")[0]
    return text + (f" {currency}" if currency else "") + (f"/{interval}" if interval else "")


def _lever_description(item: dict) -> str:
    sections = [_text(item.get("descriptionPlain"))]
    for block in item.get("lists") or []:
        if isinstance(block, dict):
            sections.append(f"{_text(block.get('text'))}\n{html_to_text(_text(block.get('content')))}".strip())
    sections.append(_text(item.get("additionalPlain")))
    return "\n\n".join(section for section in sections if section)


def _lever_jobs(board: Board, session) -> list[dict]:
    params = {"mode": "json", **board.params}
    data, _ = _get_json_with_region_fallback(session, board, f"/v0/postings/{board.token}", params)
    if not isinstance(data, list):
        raise ValueError("resposta inesperada do Lever")

    jobs = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title, url = _text(item.get("text")), _text(item.get("hostedUrl"))
        if not title or not url:
            continue
        categories = item.get("categories") if isinstance(item.get("categories"), dict) else {}
        all_locations = [loc for loc in categories.get("allLocations") or [] if isinstance(loc, str)]
        places = _unique([*all_locations, _text(categories.get("location"))])
        jobs.append(_job(
            board, title=title, url=url, places=places,
            country=infer_country(places, codes=[_text(item.get("country"))]),
            is_remote=_text(item.get("workplaceType")).lower() == "remote",
            published=_from_epoch_ms(item.get("createdAt")),
            description=_lever_description(item),
            url_direct=_text(item.get("applyUrl")),
            salary=_lever_salary(item.get("salaryRange")),
        ))
    return jobs


# ── Ashby ────────────────────────────────────────────────────────────────────

def _address_country(address) -> str:
    if not isinstance(address, dict) or not isinstance(address.get("postalAddress"), dict):
        return ""
    return _text(address["postalAddress"].get("addressCountry"))


def _ashby_jobs(board: Board, session) -> list[dict]:
    url = f"{_HOSTS[ASHBY]}/posting-api/job-board/{board.token}"
    data = _get_json(session, url, {"includeCompensation": "true"})
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ValueError("resposta inesperada do Ashby")

    jobs = []
    for item in data["jobs"]:
        if not isinstance(item, dict) or item.get("isListed") is False:
            continue
        title, url = _text(item.get("title")), _text(item.get("jobUrl"))
        if not title or not url:
            continue
        secondary = [entry for entry in item.get("secondaryLocations") or [] if isinstance(entry, dict)]
        places = _unique([_text(item.get("location")), *(_text(entry.get("location")) for entry in secondary)])
        address_countries = [_address_country(item.get("address")),
                             *(_address_country(entry.get("address")) for entry in secondary)]
        compensation = item.get("compensation") if isinstance(item.get("compensation"), dict) else {}
        jobs.append(_job(
            board, title=title, url=url, places=places,
            country=infer_country([*places, *address_countries]),
            is_remote=bool(item.get("isRemote")) or _text(item.get("workplaceType")).lower() == "remote",
            published=_parse_iso(item.get("publishedAt")),
            description=_text(item.get("descriptionPlain")) or html_to_text(_text(item.get("descriptionHtml"))),
            url_direct=_text(item.get("applyUrl")),
            salary=_text(compensation.get("compensationTierSummary")),
        ))
    return jobs


_ADAPTERS = {
    GREENHOUSE: _greenhouse_jobs, GREENHOUSE_EU: _greenhouse_jobs,
    LEVER: _lever_jobs, LEVER_EU: _lever_jobs,
    ASHBY: _ashby_jobs,
}


def list_jobs(board: Board, session) -> list[dict]:
    """
    Vagas abertas do board. Levanta requests.RequestException (rede, HTTP) ou
    ValueError (JSON inválido, formato inesperado, ATS desconhecido).
    """
    adapter = _ADAPTERS.get(board.ats)
    if adapter is None:
        raise ValueError(f"ATS desconhecido: {board.ats}")
    return adapter(board, session)
