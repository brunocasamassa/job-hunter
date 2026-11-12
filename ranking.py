# ranking.py
# Nota de 0 a 10 para ordenar o resumo do Telegram. Heurística simples e
# transparente: nicho e senioridade no título, stack na descrição,
# elegibilidade, idioma exigido e republicação.

import re

from eligibility import ELIGIBLE, MAYBE, Eligibility

_ANDROID = re.compile(r"\bandroid\b", re.IGNORECASE)
_NICHE = re.compile(
    r"\b(?:automotive|aaos|aosp|infotainment|ivi|in[-\s]vehicle|cockpit|car\s*(?:service|api|app))\b",
    re.IGNORECASE,
)
_SENIOR = re.compile(r"\b(?:senior|sr|staff|lead|principal|expert)\b", re.IGNORECASE)
_JUNIOR = re.compile(
    r"\b(?:junior|jr|intern(?:ship)?|trainee|graduate|entry[-\s]level|est[aá]gi\w*)\b",
    re.IGNORECASE,
)
_STACK = re.compile(
    r"\b(?:kotlin|jetpack\s+compose|coroutines|aosp|aaos|android\s+automotive|vhal|"
    r"car\s+api|soong|binder|hal)\b",
    re.IGNORECASE,
)

MAX_SCORE = 10


def score(job: dict, eligibility: Eligibility) -> int:
    title = job.get("title") or ""
    description = job.get("description") or ""
    points = 0

    if _ANDROID.search(title):
        points += 2
    if _NICHE.search(title):
        points += 2
    if _SENIOR.search(title):
        points += 1
    if _JUNIOR.search(title):
        points -= 3

    stack_terms = {match.group(0).lower() for match in _STACK.finditer(description)}
    points += min(len(stack_terms), 2)

    if eligibility.status == ELIGIBLE:
        points += 3
    elif eligibility.status == MAYBE:
        points += 1
    if eligibility.languages:
        points -= 2
    if job.get("repost_of"):
        points -= 1

    return max(0, min(MAX_SCORE, points))
