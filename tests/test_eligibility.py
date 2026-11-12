import pytest

from eligibility import EUROPE, ELIGIBLE, INELIGIBLE, MAYBE, classify, required_languages


def _job(country, description="", location="", title="Senior Android Engineer"):
    return {"country": country, "description": description, "location": location, "title": title}


@pytest.mark.parametrize("country", ["germany", "czech republic", "switzerland", "norway", "italy"])
def test_free_movement_countries_are_eligible(country):
    result = classify(_job(country, "Hybrid in the office."))
    assert result.status == ELIGIBLE
    assert "UE" in result.reason


def test_europe_without_country_is_eligible():
    result = classify(_job(EUROPE, "Remote within the EU."))
    assert result.status == ELIGIBLE


def test_brazil_is_eligible():
    assert classify(_job("brazil")).status == ELIGIBLE


@pytest.mark.parametrize("description", [
    "You must be authorized to work in the United States.",
    "Candidates must be located in the US.",
    "We are unable to sponsor visas for this role.",
    "No visa sponsorship is offered.",
    "Visa sponsorship is not available.",
    "This position requires security clearance.",
    "Remote (US only).",
    "You must have the right to work in the UK.",
])
def test_local_authorization_makes_visa_country_ineligible(description):
    assert classify(_job("usa", description)).status == INELIGIBLE


@pytest.mark.parametrize("description, location", [
    ("We hire remote engineers across LATAM.", "Remote"),
    ("Fully remote, candidates in Latin America welcome.", "Remote"),
    ("Work from anywhere. Async team.", "Remote"),
    ("Core hours overlap with UTC-3.", "Remote"),
    ("Contractor role.", "Remote - Americas"),
])
def test_remote_open_to_latam_is_eligible(description, location):
    assert classify(_job("usa", description, location)).status == ELIGIBLE


@pytest.mark.parametrize("description, location", [
    ("Open to candidates anywhere in the United States.", "Remote"),
    ("We serve customers worldwide.", "Remote"),
    ("Remote anywhere in the US.", "United States (Remote)"),
])
def test_phrases_that_do_not_open_to_latam(description, location):
    assert classify(_job("usa", description, location)).status == INELIGIBLE


def test_contradictory_signals_go_to_review():
    result = classify(_job("usa", "Remote across LATAM. Must be authorized to work in the US."))
    assert result.status == MAYBE


def test_sponsorship_goes_to_review():
    result = classify(_job("uk", "We offer visa sponsorship and relocation support."))
    assert result.status == MAYBE


def test_mercosur_goes_to_review():
    result = classify(_job("argentina", "Hybrid in Buenos Aires."))
    assert result.status == MAYBE
    assert "Mercosul" in result.reason


def test_missing_description_goes_to_review():
    assert classify(_job("usa", "")).status == MAYBE


def test_visa_country_without_signals_is_ineligible():
    result = classify(_job("canada", "Great team, Kotlin, Compose, CI/CD."))
    assert result.status == INELIGIBLE


@pytest.mark.parametrize("description, expected", [
    ("Fluent German is required.", ("german",)),
    ("Sehr gute Deutschkenntnisse.", ("german",)),
    ("Language skills: German (C1) and English.", ("german",)),
    ("Business fluent French.", ("french",)),
    ("German is a plus.", ()),
    ("Fluent English; ideally some Dutch.", ()),
    ("We are a German company with excellent benefits.", ()),
    ("Excellent English communication skills.", ()),
    ("Fluent Portuguese and English.", ()),
])
def test_required_languages(description, expected):
    assert required_languages(description) == expected


def test_description_written_in_german_requires_german():
    description = (
        "Wir suchen für unser Team in München eine erfahrene Android Entwicklerin oder einen "
        "erfahrenen Android Entwickler. Du arbeitest mit Kotlin und Jetpack Compose und bist "
        "für die Architektur der App verantwortlich. Wir bieten dir flexible Arbeitszeiten, "
        "ein modernes Büro und die Möglichkeit, remote zu arbeiten. Die Zusammenarbeit mit "
        "unserem Produktteam ist eng und wir freuen uns auf deine Bewerbung und deine Ideen."
    )
    assert required_languages(description) == ("german",)


def test_languages_are_reported_even_when_eligible():
    result = classify(_job("germany", "Fluent German is required."))
    assert result.status == ELIGIBLE
    assert result.languages == ("german",)
