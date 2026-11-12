import pytest

from eligibility import EUROPE
from locations import countries_in, infer_country, mentions_remote_europe


@pytest.mark.parametrize("place, country", [
    ("Berlin, Germany", "germany"),
    ("München", "germany"),
    ("Remote - Brazil", "brazil"),
    ("São Paulo", "brazil"),
    ("Kraków, Poland", "poland"),
    ("Warszawa", "poland"),
    ("Łódź", "poland"),
    ("Cluj-Napoca / Timisoara / Iasi", "romania"),
    ("Göteborg", "sweden"),
    ("Amsterdam, The Netherlands", "netherlands"),
    ("Remote - Europe", EUROPE),
    ("EMEA Remote", EUROPE),
    ("Dublin, Ireland", "ireland"),
    ("Belfast, Northern Ireland, Remote", "uk"),
    ("London, UK", "uk"),
    ("Remote - US", "usa"),
])
def test_country_from_place(place, country):
    assert infer_country([place]) == country


@pytest.mark.parametrize("place", ["Remote", "Hybrid", "", "Anywhere"])
def test_unknown_place_is_empty(place):
    assert infer_country([place]) == ""


def test_prefers_a_place_where_you_can_work():
    assert infer_country(["New York, NY", "Lisbon"]) == "portugal"
    assert infer_country(["Remote - US", "Remote - Europe"]) == EUROPE
    assert infer_country(["Toronto", "Buenos Aires"]) == "argentina"  # Mercosul antes do resto


def test_iso_code_from_lever():
    assert infer_country([], codes=["DE"]) == "germany"
    assert infer_country([], codes=["de "]) == "germany"
    assert infer_country([], codes=["XX", ""]) == ""
    # código do local principal fora da UE, mas um dos locais é na UE
    assert infer_country(["Belgrade, Serbia", "Madrid"], codes=["RS"]) == "spain"


def test_countries_in_keeps_order():
    assert countries_in("Paris / Berlin / Remote - US") == ["france", "germany", "usa"]


def test_words_inside_other_words_do_not_match():
    assert countries_in("Ruse Business Park") == []  # "us" dentro de "business"
    assert countries_in("Euroland") == []


@pytest.mark.parametrize("text", [
    "This role is fully remote within the EU.",
    "You can work from anywhere in Europe.",
    "Candidates must be based in the EEA.",
])
def test_remote_europe_in_description(text):
    assert mentions_remote_europe(text)


@pytest.mark.parametrize("text", [
    "We have offices across Europe and the US. This role is in New York.",
    "Must be located in the United States.",
    "",
])
def test_no_remote_europe_in_description(text):
    assert not mentions_remote_europe(text)
