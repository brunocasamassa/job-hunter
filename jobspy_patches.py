# jobspy_patches.py
# Workarounds para bugs do JobSpy 1.1.82 que não conseguimos resolver upstream.
# Cada patch tem comentário descrevendo o bug — se JobSpy corrigir,
# basta apagar este arquivo e a linha `import jobspy_patches`.

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

from jobspy.exception import GlassdoorException
from jobspy.glassdoor import Glassdoor, log
from jobspy.glassdoor.util import get_cursor_for_page


# ── Patch 1: Glassdoor._fetch_jobs_page tolera GraphQL partial errors ──
#
# Bug: jobspy/glassdoor/__init__.py:123-124 aborta toda a página se o JSON
# tem qualquer chave `errors`, violando a spec do GraphQL (resposta pode
# ter `data` E `errors` ao mesmo tempo — "partial errors").
#
# Caso real: o microsserviço interno do Glassdoor que gera `jobsPageSeoData`
# está com erro de DNS, devolve `errors` com path `["jobListings",
# "jobsPageSeoData"]`. Mas `data.jobListings.jobListings` vem completo.
# JobSpy joga tudo fora. Este patch só aborta se o array de vagas estiver
# de fato ausente.


def _patched_fetch_jobs_page(
    self, scraper_input, location_id, location_type, page_num, cursor
):
    jobs = []
    self.scraper_input = scraper_input
    try:
        payload = self._add_payload(location_id, location_type, page_num, cursor)
        response = self.session.post(
            f"{self.base_url}/graph",
            timeout_seconds=15,
            data=payload,
        )
        if response.status_code != 200:
            raise GlassdoorException(f"bad response status code: {response.status_code}")
        res_json = response.json()[0]

        if "errors" in res_json:
            data = res_json.get("data") or {}
            job_listings = (data.get("jobListings") or {}).get("jobListings")
            if not job_listings:
                raise ValueError(f"GraphQL errors sem dados utilizáveis: {res_json['errors']}")
            log.warning(f"Glassdoor partial errors (ignorados): {res_json['errors']}")
    except (
        requests.exceptions.ReadTimeout,
        GlassdoorException,
        ValueError,
        Exception,
    ) as e:
        log.error(f"Glassdoor: {str(e)}")
        return jobs, None

    jobs_data = res_json["data"]["jobListings"]["jobListings"]

    with ThreadPoolExecutor(max_workers=self.jobs_per_page) as executor:
        future_to_job_data = {
            executor.submit(self._process_job, job): job for job in jobs_data
        }
        for future in as_completed(future_to_job_data):
            try:
                job_post = future.result()
                if job_post:
                    jobs.append(job_post)
            except Exception as exc:
                raise GlassdoorException(f"Glassdoor generated an exception: {exc}")

    return jobs, get_cursor_for_page(
        res_json["data"]["jobListings"]["paginationCursors"], page_num + 1
    )


Glassdoor._fetch_jobs_page = _patched_fetch_jobs_page


# ── Patch 2: Glassdoor._get_location faz URL-encode do termo ───────────
#
# Bug: jobspy/glassdoor/__init__.py:261 interpola `location` direto na URL
# sem URL-encode. Domínios glassdoor.com e glassdoor.co.uk rejeitam com 400
# (body vazio) quando o termo tem espaço literal. Domínios regionais toleram.
#
# Confirmado em teste isolado: `term=United States` → 400, mesma request com
# `term=United%20States` → 200. Aplicamos `urllib.parse.quote` no termo.


def _patched_get_location(self, location, is_remote):
    if not location or is_remote:
        return "11047", "STATE"
    url = (
        f"{self.base_url}/findPopularLocationAjax.htm"
        f"?maxLocationsToReturn=10&term={quote(location)}"
    )
    res = self.session.get(url)
    if res.status_code != 200:
        if res.status_code == 429:
            log.error("429 Response - Blocked by Glassdoor for too many requests")
            return None, None
        log.error(f"Glassdoor response status code {res.status_code}")
        return None, None
    items = res.json()

    if not items:
        raise ValueError(f"Location '{location}' not found on Glassdoor")
    location_type = items[0]["locationType"]
    if location_type == "C":
        location_type = "CITY"
    elif location_type == "S":
        location_type = "STATE"
    elif location_type == "N":
        location_type = "COUNTRY"
    return int(items[0]["locationId"]), location_type


Glassdoor._get_location = _patched_get_location
