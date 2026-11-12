# locations.py
# Descobre o país de uma vaga a partir do texto de local ("Berlin, Germany",
# "Remote - Brazil", "Kraków") ou de um código ISO ("DE"). Usado pelo radar:
# no JobSpy o país vem da busca; nas APIs dos ATS cada vaga diz onde é.
# Os nomes de país são os mesmos de eligibility.py.

import re
import unicodedata
from typing import Iterable

from eligibility import EUROPE, FREE_MOVEMENT_COUNTRIES, HOME_COUNTRY, MERCOSUR_RESIDENCE_COUNTRIES

# País → nomes e cidades que aparecem nos locais das vagas (sem acento; o texto
# também é comparado sem acento). Só precisa ser completo onde você pode
# trabalhar: país não reconhecido fica vazio e a descrição decide.
_PLACES = {
    "austria": "austria osterreich vienna wien graz linz salzburg innsbruck klagenfurt",
    "belgium": "belgium belgie belgique brussels bruxelles antwerp ghent leuven",
    "bulgaria": "bulgaria sofia plovdiv varna burgas",
    "croatia": "croatia hrvatska zagreb split rijeka osijek",
    "cyprus": "cyprus limassol nicosia larnaca",
    "czech republic": "czech_republic czechia cesko prague praha brno ostrava plzen pilsen mlada_boleslav",
    "denmark": "denmark danmark copenhagen kobenhavn aarhus",
    "estonia": "estonia eesti tallinn tartu",
    "finland": "finland suomi helsinki espoo tampere oulu turku vantaa",
    "france": "france paris lyon toulouse nice sophia_antipolis nantes bordeaux marseille lille "
              "grenoble rennes montpellier guyancourt",
    "germany": "germany deutschland berlin munich munchen muenchen hamburg frankfurt cologne koln "
               "stuttgart dusseldorf duesseldorf leipzig dresden nuremberg nurnberg ingolstadt "
               "wolfsburg karlsruhe hannover bonn mannheim heidelberg darmstadt braunschweig "
               "weissach sindelfingen aachen bremen essen dortmund potsdam",
    "greece": "greece athens thessaloniki",
    "hungary": "hungary magyarorszag budapest debrecen szeged",
    "ireland": "ireland dublin cork galway limerick",
    "italy": "italy italia milan milano turin torino rome roma bologna florence firenze naples "
             "napoli genoa genova padua padova modena",
    "latvia": "latvia latvija riga",
    "lithuania": "lithuania lietuva vilnius kaunas",
    "luxembourg": "luxembourg",
    "malta": "malta valletta",
    "netherlands": "netherlands the_netherlands nederland holland amsterdam eindhoven rotterdam "
                   "utrecht the_hague den_haag delft groningen",
    "poland": "poland polska warsaw warszawa krakow cracow wroclaw gdansk katowice poznan lodz "
              "szczecin lublin bydgoszcz gdynia",
    "portugal": "portugal lisbon lisboa porto braga coimbra aveiro",
    "romania": "romania bucharest bucuresti cluj cluj-napoca timisoara iasi brasov sibiu "
               "targu_mures oradea craiova constanta",
    "slovakia": "slovakia slovensko bratislava kosice zilina",
    "slovenia": "slovenia slovenija ljubljana maribor",
    "spain": "spain espana barcelona madrid valencia malaga seville sevilla bilbao zaragoza "
             "martorell",
    "sweden": "sweden sverige stockholm gothenburg goteborg malmo lund uppsala linkoping",
    "iceland": "iceland reykjavik",
    "liechtenstein": "liechtenstein",
    "norway": "norway norge oslo bergen trondheim",
    "switzerland": "switzerland schweiz suisse svizzera zurich geneva geneve basel bern lausanne zug",
    "brazil": "brazil brasil sao_paulo rio_de_janeiro campinas belo_horizonte curitiba "
              "florianopolis porto_alegre recife brasilia salvador fortaleza goiania manaus "
              "sao_jose_dos_campos joinville blumenau ribeirao_preto",
    "argentina": "argentina buenos_aires cordoba rosario mendoza",
    "chile": "chile santiago valparaiso",
    "colombia": "colombia bogota medellin cali",
    "uruguay": "uruguay montevideo",
    "peru": "peru lima",
    "paraguay": "paraguay asuncion",
    "bolivia": "bolivia",
    "ecuador": "ecuador quito",
    # Fora da UE: reconhecer evita que "Northern Ireland" vire Irlanda, por exemplo.
    "uk": "uk united_kingdom england scotland wales northern_ireland great_britain london "
          "manchester edinburgh belfast glasgow bristol oxford",
    "usa": "usa us u.s. united_states new_york san_francisco seattle boston austin chicago "
           "los_angeles palo_alto mountain_view sunnyvale",
    "canada": "canada toronto montreal vancouver",
    "mexico": "mexico mexico_city guadalajara monterrey",
    "india": "india bangalore bengaluru hyderabad pune chennai noida gurgaon",
    "serbia": "serbia belgrade novi_sad",
    "ukraine": "ukraine kyiv kiev lviv kharkiv",
    "turkey": "turkey turkiye istanbul",
    "israel": "israel tel_aviv",
    "united arab emirates": "united_arab_emirates uae dubai abu_dhabi",
    "japan": "japan tokyo",
    "china": "china shanghai beijing shenzhen",
    "south korea": "south_korea korea seoul",
    "singapore": "singapore",
    "australia": "australia sydney melbourne",
}

# Região inteira: "Remote - Europe", "EU", "EMEA". Cidadão da UE pode morar
# em qualquer país do bloco.
_EUROPE_WORDS = "europe european_union eu eea emea"

# Código ISO 3166-1 alpha-2, como o Lever manda no campo `country`.
ISO_CODES = {
    "AT": "austria", "BE": "belgium", "BG": "bulgaria", "HR": "croatia", "CY": "cyprus",
    "CZ": "czech republic", "DK": "denmark", "EE": "estonia", "FI": "finland", "FR": "france",
    "DE": "germany", "GR": "greece", "HU": "hungary", "IE": "ireland", "IT": "italy",
    "LV": "latvia", "LT": "lithuania", "LU": "luxembourg", "MT": "malta", "NL": "netherlands",
    "PL": "poland", "PT": "portugal", "RO": "romania", "SK": "slovakia", "SI": "slovenia",
    "ES": "spain", "SE": "sweden", "IS": "iceland", "LI": "liechtenstein", "NO": "norway",
    "CH": "switzerland", "BR": "brazil", "AR": "argentina", "CL": "chile", "CO": "colombia",
    "UY": "uruguay", "PE": "peru", "PY": "paraguay", "BO": "bolivia", "EC": "ecuador",
    "GB": "uk", "US": "usa", "CA": "canada", "MX": "mexico", "IN": "india", "RS": "serbia",
    "UA": "ukraine", "TR": "turkey", "IL": "israel", "AE": "united arab emirates",
    "JP": "japan", "CN": "china", "KR": "south korea", "SG": "singapore", "AU": "australia",
}

_WORKABLE = FREE_MOVEMENT_COUNTRIES | {EUROPE, HOME_COUNTRY}

# Letras que o NFKD não separa do acento.
_EXTRA_FOLD = str.maketrans({"ł": "l", "ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "đ": "d"})


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower().translate(_EXTRA_FOLD))
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _build_alias_map() -> dict[str, str]:
    aliases = {}
    for country, words in _PLACES.items():
        for word in words.split():
            aliases[word.replace("_", " ")] = country
    for word in _EUROPE_WORDS.split():
        aliases[word.replace("_", " ")] = EUROPE
    return aliases


_ALIASES = _build_alias_map()
# Mais longo primeiro: "northern ireland" casa antes de "ireland".
_ALIAS_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:"
    + "|".join(re.escape(alias) for alias in sorted(_ALIASES, key=len, reverse=True))
    + r")(?![a-z0-9])"
)

_REMOTE_EUROPE = re.compile(
    r"\b(?:remote|remotely|anywhere|work(?:ing)?\s+from|located|based|reside|residing)\b"
    r"[^.!?\n]{0,40}?\b(?:in|within|across|from)\s+(?:the\s+)?"
    r"(?:eu|europe|european\s+union|eea|emea)\b",
    re.IGNORECASE,
)


def countries_in(text: str) -> list[str]:
    """Países citados no texto, na ordem em que aparecem."""
    return [_ALIASES[match.group(0)] for match in _ALIAS_PATTERN.finditer(_fold(text or ""))]


def infer_country(places: Iterable[str] = (), codes: Iterable[str] = ()) -> str:
    """
    País da vaga. Com vários locais, prefere um onde você pode trabalhar
    ("New York / Lisbon" → portugal), depois o Mercosul, depois o primeiro
    reconhecido. Vazio se nenhum for reconhecido.
    """
    found = [ISO_CODES[code.strip().upper()] for code in codes
             if code and code.strip().upper() in ISO_CODES]
    for place in places:
        found.extend(countries_in(place))
    for preferred in (_WORKABLE, MERCOSUR_RESIDENCE_COUNTRIES):
        for country in found:
            if country in preferred:
                return country
    return found[0] if found else ""


def mentions_remote_europe(text: str) -> bool:
    """A descrição diz que a vaga é remota/baseada na Europa ("remote within the EU")."""
    return _REMOTE_EUROPE.search(text or "") is not None
