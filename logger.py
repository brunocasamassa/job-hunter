# logger.py
# Configuração de logging para depurar o Glassdoor.
# Basta `import logger` em qualquer módulo para ativar.

import logging
import requests
import tls_client

# Eleva verbosidade do JobSpy e bibliotecas HTTP para depurar Glassdoor.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
for _name in ("JobSpy", "JobSpy:Glassdoor", "JobSpy:LinkedIn", "JobSpy:Indeed"):
    logging.getLogger(_name).setLevel(logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.INFO)


def _log_gd_request(method, url, headers, data, json_body):
    """Imprime detalhes de uma request HTTP destinada ao Glassdoor."""
    print(f"\n   ━━━ HTTP {method} {url}")
    headers = headers or {}
    csrf = headers.get("gd-csrf-token") or headers.get("Gd-Csrf-Token")
    ua = headers.get("user-agent") or headers.get("User-Agent")
    print(f"       gd-csrf-token: {csrf!r}")
    if ua:
        print(f"       user-agent:    {ua[:90]}")
    if data:
        print(f"       data:          {str(data)[:300]}")
    if json_body:
        print(f"       json:          {str(json_body)[:300]}")


def _log_gd_response(response):
    """Imprime status e corpo da resposta do Glassdoor.
    - 4xx/5xx: body curto (até 600 chars).
    - 200 contendo `"errors":` em qualquer ponto: janela em volta do match (até 1500 chars).
    - 200 pequeno: body curto.
    - 200 grande sem `"errors":`: primeiros 600 chars (sanity check).
    """
    text = getattr(response, "text", "") or ""
    size = len(text)
    print(f"       ← {response.status_code} ({size} bytes)")
    if response.status_code >= 400:
        print(f"       ✗ body[:600]: {text[:600]!r}")
        return
    if response.status_code != 200:
        return
    idx = text.find('"errors":')
    if idx >= 0:
        start = max(0, idx - 30)
        end = min(len(text), idx + 1500)
        print(f"       ⚠ errors window[{start}:{end}]: {text[start:end]!r}")
    elif size < 2000:
        print(f"       ⚠ corpo curto/json: {text[:600]!r}")
    else:
        print(f"       body[:600]: {text[:600]!r}")


# Patch 1: requests.Session.request — cobre LinkedIn/Indeed e _fetch_job_description
# do Glassdoor (que usa requests.post direto, sem passar pela sessão TLS).
_original_session_request = requests.Session.request


def _logged_session_request(self, method, url, *args, **kwargs):
    is_gd = "glassdoor" in str(url).lower()
    if is_gd:
        sent_headers = {**(self.headers or {}), **(kwargs.get("headers") or {})}
        _log_gd_request(method, url, sent_headers, kwargs.get("data"), kwargs.get("json"))
    try:
        response = _original_session_request(self, method, url, *args, **kwargs)
    except Exception as exc:
        if is_gd:
            print(f"       ✗ EXCEÇÃO de rede: {type(exc).__name__}: {exc}")
        raise
    if is_gd:
        _log_gd_response(response)
    return response


requests.Session.request = _logged_session_request


# Patch 2: tls_client.Session.execute_request — é o caminho REAL do Glassdoor.
# JobSpy usa TLSRotating(tls_client.Session, ...) com fingerprint TLS de browser
# pra burlar detecção de bot. Todas as chamadas .get()/.post() dessa sessão
# desembocam em execute_request.
_original_tls_execute = tls_client.Session.execute_request


def _logged_tls_execute(
    self,
    method,
    url,
    params=None,
    data=None,
    headers=None,
    cookies=None,
    json=None,
    *args,
    **kwargs,
):
    is_gd = "glassdoor" in str(url).lower()
    if is_gd:
        sent_headers = {**(getattr(self, "headers", {}) or {}), **(headers or {})}
        _log_gd_request(method, url, sent_headers, data, json)
    try:
        response = _original_tls_execute(
            self, method, url,
            params=params, data=data, headers=headers,
            cookies=cookies, json=json,
            *args, **kwargs,
        )
    except Exception as exc:
        if is_gd:
            print(f"       ✗ EXCEÇÃO de rede: {type(exc).__name__}: {exc}")
        raise
    if is_gd:
        _log_gd_response(response)
    return response


tls_client.Session.execute_request = _logged_tls_execute


def debug_scrape(site_names, search_term, location, country_indeed, hours_old, results_wanted=20):
    """
    Wrapper em scrape_jobs com logging detalhado:
      - antes da chamada, imprime o fallback_token do Glassdoor (se aplicável);
      - depois, imprime contagem bruta e breakdown por site;
      - em erro, imprime tipo, mensagem e traceback completo, e re-levanta.
    Retorna o DataFrame retornado (possivelmente vazio) ou None.
    """
    import traceback
    from jobspy import scrape_jobs

    if "glassdoor" in site_names:
        try:
            import jobspy.glassdoor.constant as _gd_const
            print(f"   🔑 fallback_token: {getattr(_gd_const, 'fallback_token', None)!r}")
        except Exception as _e:
            print(f"   ⚠️  Não inspecionou token: {type(_e).__name__}: {_e}")

    try:
        jobs_df = scrape_jobs(
            site_name=site_names,
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            country_indeed=country_indeed,
            verbose=2,
        )
    except Exception as e:
        print(f"  ❌ Erro em {location}: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise

    if jobs_df is None:
        print(f"  ⚠️  scrape_jobs retornou None em {location}")
        return None
    if jobs_df.empty:
        print(f"  ⚠️  DataFrame vazio em {location} (0 vagas brutas)")
        return jobs_df

    print(f"  📊 {len(jobs_df)} vaga(s) brutas em {location}")
    if "site" in jobs_df.columns:
        print(f"  🏷️  Por site: {jobs_df['site'].value_counts().to_dict()}")
    return jobs_df
