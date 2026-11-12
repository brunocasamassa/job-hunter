# dedupe.py
# Reconhece a mesma vaga em sites diferentes (ou republicada com outra URL)
# pela "impressão digital" empresa + título + país, normalizados.

import re
import unicodedata

# Títulos europeus trazem "(m/w/d)", "(f/m/x)", "all genders"...
_BRACKETS = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_GENDER_TAGS = re.compile(
    r"\b[mwfdhx]\s*/\s*[mwfdhx](?:\s*/\s*[mwfdhx])?\b|\ball\s+genders?\b",
    re.IGNORECASE,
)
_COMPANY_SUFFIXES = re.compile(
    r"\b(?:gmbh|ag|se|kg|inc|llc|ltd|limited|corp|corporation|co|plc|sa|sl|srl|spa|bv|nv|"
    r"sp\s*z\s*o\s*o|sp\s*z\s*oo|as|ab|oy|kft|sro|sas|sarl)\b",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_MISSING_COMPANY = {"", "n a", "na", "none", "nan"}


def _fold(text: str) -> str:
    """Minúsculas e sem acento ("München" → "munchen")."""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def normalize_title(title: str) -> str:
    text = _GENDER_TAGS.sub(" ", _BRACKETS.sub(" ", _fold(title)))
    return " ".join(_NON_ALNUM.sub(" ", text).split())


def normalize_company(company: str) -> str:
    text = _fold(company).replace(".", "").replace(",", " ")
    text = _COMPANY_SUFFIXES.sub(" ", _NON_ALNUM.sub(" ", text))
    return " ".join(text.split())


def fingerprint(job: dict) -> str | None:
    """'empresa|título|país' normalizados; None se faltar empresa ou título."""
    company = normalize_company(job.get("company") or "")
    title = normalize_title(job.get("title") or "")
    if company in _MISSING_COMPANY or not title:
        return None
    country = (job.get("country") or "").strip().lower()
    return f"{company}|{title}|{country}"


def _completeness(job: dict) -> tuple[bool, int]:
    return bool(job.get("url_direct")), len(job.get("description") or "")


def split_duplicates(jobs: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Separa as vagas repetidas numa mesma execução (mesmo `fingerprint`).
    Fica a versão mais completa — com link do site da empresa e, depois, com
    a maior descrição; as demais voltam como duplicatas. Mantém a ordem.
    """
    unique: list[dict] = []
    duplicates: list[dict] = []
    position_by_fingerprint: dict[str, int] = {}

    for job in jobs:
        key = job.get("fingerprint")
        if key is None:
            unique.append(job)
            continue
        if key not in position_by_fingerprint:
            position_by_fingerprint[key] = len(unique)
            unique.append(job)
            continue
        position = position_by_fingerprint[key]
        if _completeness(job) > _completeness(unique[position]):
            duplicates.append(unique[position])
            unique[position] = job
        else:
            duplicates.append(job)
    return unique, duplicates
