# eligibility.py
# Diz se você pode trabalhar na vaga, a partir do país da busca, do local e da
# descrição. É heurística (regex), não parecer jurídico: na dúvida a vaga vai
# para "confira" em vez de ser escondida.
#
# Ordem das regras:
#   1. País da UE/EEE ou Suíça, ou "Europa" sem país → pode (cidadania italiana, sem visto)
#   2. Brasil → pode
#   3. Texto diz que aceita LatAm/Brasil/qualquer lugar → pode
#      (se também exigir autorização local → confira)
#   4. Texto exige autorização/residência local → não pode
#   5. Mercosul → confira (residência facilitada para brasileiros)
#   6. Oferece visto/relocação → confira
#   7. Sem descrição → confira
#   8. Resto (país que exige visto, sem sinal de abertura) → não pode

import re
from dataclasses import dataclass

ELIGIBLE = "eligible"
MAYBE = "maybe"
INELIGIBLE = "ineligible"

# Cidadão da UE trabalha sem permissão de trabalho na UE, no EEE (Islândia,
# Liechtenstein, Noruega) e na Suíça. Nomes como no country_indeed do JobSpy.
FREE_MOVEMENT_COUNTRIES = frozenset({
    "austria", "belgium", "bulgaria", "croatia", "cyprus", "czech republic",
    "czechia", "denmark", "estonia", "finland", "france", "germany", "greece",
    "hungary", "ireland", "italy", "latvia", "lithuania", "luxembourg", "malta",
    "netherlands", "poland", "portugal", "romania", "slovakia", "slovenia",
    "spain", "sweden",
    "iceland", "liechtenstein", "norway",
    "switzerland",
})

HOME_COUNTRY = "brazil"

# Vaga da Europa sem país específico ("Remote - Europe", "EMEA"), vinda do
# radar: dá para morar em qualquer país do bloco.
EUROPE = "europe"

# Acordo de Residência do Mercosul: brasileiro pede, no próprio país,
# residência temporária de 2 anos com direito a trabalhar.
MERCOSUR_RESIDENCE_COUNTRIES = frozenset({
    "argentina", "bolivia", "chile", "colombia", "ecuador", "paraguay", "peru", "uruguay",
})

# Idiomas que você fala. Vaga que exige outro idioma ganha aviso (não some).
SPOKEN_LANGUAGES = frozenset({"english", "portuguese"})

LANGUAGE_LABELS = {
    "german": "alemão", "french": "francês", "dutch": "holandês",
    "swedish": "sueco", "danish": "dinamarquês", "norwegian": "norueguês",
    "finnish": "finlandês", "polish": "polonês", "czech": "tcheco",
    "hungarian": "húngaro", "italian": "italiano", "spanish": "espanhol",
    "portuguese": "português", "english": "inglês",
}


@dataclass(frozen=True)
class Eligibility:
    status: str                      # ELIGIBLE / MAYBE / INELIGIBLE
    reason: str                      # texto curto para o alerta
    languages: tuple[str, ...] = ()  # idiomas exigidos que você não fala


# ── Sinais na descrição ──────────────────────────────────────────────────────

_VISA_COUNTRIES = (
    r"(?:the\s+)?(?:u\.?\s?s\.?(?:a\.?)?|united\s+states|north\s+america|"
    r"u\.?k\.?|united\s+kingdom|great\s+britain|canada|mexico|singapore|thailand|indonesia)"
)

_LOCAL_AUTH_ONLY = re.compile(
    rf"""
      \b(?:legally\s+)?(?:authori[sz]ed|eligible|permitted|able)\s+to\s+work\s+in\s+{_VISA_COUNTRIES}\b
    | \bright\s+to\s+work\s+in\s+{_VISA_COUNTRIES}\b
    | \b(?:must|need\s+to|required\s+to|should)\s+(?:be\s+)?(?:currently\s+)?
        (?:located|based|resid(?:e|ent|ing)|liv(?:e|ing))\s+(?:in|within)\s+{_VISA_COUNTRIES}\b
    | \b{_VISA_COUNTRIES}\s+(?:citizens?|citizenship|persons?|residents?)\s+(?:only|required)\b
    | \b(?:no|unable\s+to|not\s+able\s+to|not\s+in\s+a\s+position\s+to|cannot|can\s?not|
          will\s+not|won'?t|do(?:es)?\s+not|are\s+not\s+able\s+to)
        \s+(?:offer\s+|provide\s+|support\s+)?(?:any\s+)?(?:visa\s+|work\s+permit\s+|immigration\s+)?
        sponsor(?:ship)?\b
    | \b(?:visa\s+|work\s+permit\s+)?sponsorship\s+(?:is\s+)?(?:not|un)\s*available\b
    | \b(?:security|government)\s+clearance\b
    | \bgreen\s+card\b
    | \bremote\s*(?:[-–—:(,/]\s*)?{_VISA_COUNTRIES}\s*(?:only|based)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# "anywhere in the US" não conta como abertura.
_REGION_WORDS = (
    r"(?:latam|latin\s+america|south\s+america|americas|brazil|brasil|worldwide|globally|"
    rf"anywhere(?!\s+(?:in|within|across)\s+{_VISA_COUNTRIES}))"
)
# Proximidade dentro da mesma frase: separadores não atravessam . ! ? ou quebra de linha.
_SEP = r"[^\w.!?\n]+"
_OPEN_TO_LATAM = re.compile(
    rf"""
      \b(?:remote|remotely|hire|hiring|hires|candidates?|applicants?|work(?:ing)?\s+from|
          located|location|open\s+to|contractors?)\b{_SEP}(?:\w+{_SEP}){{0,4}}?{_REGION_WORDS}\b
    | \b{_REGION_WORDS}\b{_SEP}(?:\w+{_SEP}){{0,3}}?
        (?:remote|candidates?|applicants?|hires?|hiring|time\s*zones?|contractors?)\b
    | \b(?:gmt|utc)\s*[-−–]\s*0?3\b
    | \bbrt\b
    """,
    re.IGNORECASE | re.VERBOSE,
)
_LOCATION_OPEN = re.compile(
    rf"\b(?:latam|latin\s+america|south\s+america|americas|brazil|brasil|worldwide|"
    rf"anywhere(?!\s+(?:in|within|across)\s+{_VISA_COUNTRIES}))\b",
    re.IGNORECASE,
)

_SPONSORSHIP = re.compile(
    r"""
      \b(?:visa|work\s+permit|immigration)\s+(?:sponsorship|support|assistance)\s+
        (?:is\s+)?(?:available|provided|offered|possible|included)\b
    | \b(?:we|company)\s+(?:can|will|do|are\s+able\s+to)\s+sponsor\b
    | \b(?:offer|offers|offering|provide|provides|providing|including|includes|with)\s+
        (?:full\s+|a\s+)?(?:visa\s+sponsorship|relocation(?:\s+(?:package|support|assistance|budget|allowance))?)\b
    | \brelocation\s+(?:package|assistance|support|bonus|budget|allowance)\s+
        (?:is\s+)?(?:available|provided|offered|included)\b
    | \b(?:visa\s+sponsorship|relocation)\s+(?:available|provided|offered)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


# ── Idioma exigido ───────────────────────────────────────────────────────────

_LANGUAGE_NAMES = {
    "german": r"german|deutsch\w*",
    "french": r"french|fran[cç]ais\w*",
    "dutch": r"dutch|nederlands",
    "swedish": r"swedish|svenska",
    "danish": r"danish|dansk",
    "norwegian": r"norwegian|norsk",
    "finnish": r"finnish|suomi",
    "polish": r"polish|polski\w*",
    "czech": r"czech|[cč]e[sš]tin\w*",
    "hungarian": r"hungarian|magyar",
    "italian": r"italian|italiano",
    "spanish": r"spanish|espa[nñ]ol|castellano",
    "portuguese": r"portuguese|portugu[eê]s",
    "english": r"english",
}
_LANGUAGE_PATTERNS = {
    lang: re.compile(rf"\b(?:{names})\b", re.IGNORECASE) for lang, names in _LANGUAGE_NAMES.items()
}
# Nível que, perto do idioma, já indica exigência ("fluent German", "German C1").
_STRONG_LEVEL = re.compile(
    r"\b(?:fluen\w*|native|mother\s+tongue|business[-\s]?(?:level|fluent)|proficien\w*|c1|c2|b2|"
    r"flie(?:ß|ss)end\w*|verhandlungssicher\w*|muttersprach\w*|courant\w*|ma[iî]tris\w*)\b",
    re.IGNORECASE,
)
# Nível genérico: só conta se a frase também falar de idioma/comunicação.
_WEAK_LEVEL = re.compile(
    r"\b(?:excellent|very\s+good|good|strong|solid|advanced|required|requirement|mandatory|must|"
    r"essential|sehr\s+gute?\w*|gute\w*|zwingend|erforderlich|vorausgesetzt|exig\w*|obligatoire)\b",
    re.IGNORECASE,
)
_LANGUAGE_CONTEXT = re.compile(
    r"\b(?:skills?|languages?|speak\w*|spoken|written|verbal|communication|command|knowledge|"
    r"\w*kenntnisse|sprach\w*|langue)\b",
    re.IGNORECASE,
)
_OPTIONAL = re.compile(
    r"\b(?:plus|nice[-\s]to[-\s]have|advantage\w*|bonus|desirable|preferred|beneficial|benefit|"
    r"welcome|ideally|von\s+vorteil|wünschenswert|atout)\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"[.\n;•·!?]+")
_LEVEL_WINDOW_CHARS = 30

# Descrição escrita no idioma local também indica que ele é exigido.
_STOPWORDS = {
    "german": {"und", "der", "die", "das", "mit", "für", "wir", "sie", "ist", "nicht",
               "auf", "bei", "eine", "einen", "deine", "ihre", "werden", "oder", "zu", "von"},
    "french": {"et", "le", "la", "les", "des", "pour", "nous", "vous", "une", "est",
               "avec", "dans", "sur", "votre", "du", "au"},
    "dutch": {"het", "van", "voor", "wij", "jij", "je", "een", "met", "zijn", "bij",
              "ons", "jouw", "naar", "ook", "niet"},
}
_WORD = re.compile(r"[a-zäöüßàâçéèêëîïôûùÿœæ]+")
_MIN_TOKENS_FOR_LANGUAGE_GUESS = 40
_STOPWORD_RATIO = 0.08


def _near(first: re.Match, second: re.Match, window: int) -> bool:
    gap = max(first.start(), second.start()) - min(first.end(), second.end())
    return gap <= window


def _written_in(text: str) -> str | None:
    tokens = _WORD.findall(text.lower())[:600]
    if len(tokens) < _MIN_TOKENS_FOR_LANGUAGE_GUESS:
        return None
    best_lang, best_ratio = None, 0.0
    for lang, words in _STOPWORDS.items():
        ratio = sum(token in words for token in tokens) / len(tokens)
        if ratio > best_ratio:
            best_lang, best_ratio = lang, ratio
    return best_lang if best_ratio >= _STOPWORD_RATIO else None


def required_languages(description: str) -> tuple[str, ...]:
    """Idiomas que a vaga parece exigir e que não estão em SPOKEN_LANGUAGES."""
    found = set()
    for sentence in _SENTENCE_SPLIT.split(description or ""):
        if not sentence.strip() or _OPTIONAL.search(sentence):
            continue
        has_context = bool(_LANGUAGE_CONTEXT.search(sentence))
        strong = list(_STRONG_LEVEL.finditer(sentence))
        weak = list(_WEAK_LEVEL.finditer(sentence)) if has_context else []
        for lang, pattern in _LANGUAGE_PATTERNS.items():
            if lang in SPOKEN_LANGUAGES:
                continue
            for mention in pattern.finditer(sentence):
                if any(_near(mention, level, _LEVEL_WINDOW_CHARS) for level in strong + weak):
                    found.add(lang)
                    break

    written = _written_in(description or "")
    if written and written not in SPOKEN_LANGUAGES:
        found.add(written)
    return tuple(sorted(found))


def classify(job: dict) -> Eligibility:
    country = (job.get("country") or "").strip().lower()
    location = job.get("location") or ""
    description = job.get("description") or ""
    text = f"{job.get('title') or ''}\n{location}\n{description}"
    languages = required_languages(description)

    if country in FREE_MOVEMENT_COUNTRIES or country == EUROPE:
        return Eligibility(ELIGIBLE, "🇪🇺 UE/EEE/Suíça — sem visto", languages)
    if country == HOME_COUNTRY:
        return Eligibility(ELIGIBLE, "🇧🇷 Brasil", languages)

    open_to_latam = bool(
        _OPEN_TO_LATAM.search(job.get("title") or "")
        or _OPEN_TO_LATAM.search(description)
        or _LOCATION_OPEN.search(location)
    )
    local_only = bool(_LOCAL_AUTH_ONLY.search(text))

    if open_to_latam and local_only:
        return Eligibility(MAYBE, "⚠️ Sinais contraditórios sobre o local — confira", languages)
    if open_to_latam:
        return Eligibility(ELIGIBLE, "🌎 Remoto aberto a LatAm/Brasil", languages)
    if local_only:
        return Eligibility(INELIGIBLE, "❌ Exige autorização/residência local", languages)
    if country in MERCOSUR_RESIDENCE_COUNTRIES:
        return Eligibility(MAYBE, "🌎 Mercosul — residência facilitada", languages)
    if _SPONSORSHIP.search(text):
        return Eligibility(MAYBE, "⚠️ Oferece visto/relocação", languages)
    if not description.strip():
        return Eligibility(MAYBE, "❓ Sem descrição — confira o local", languages)
    return Eligibility(INELIGIBLE, "❌ Não diz que aceita LatAm", languages)
