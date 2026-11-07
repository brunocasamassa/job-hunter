import pytest

import job_scraper
from job_scraper import _clean, _format_salary, is_relevant


@pytest.mark.parametrize("title", [
    "Senior AOSP Engineer",
    "Infotainment Software Engineer - Automotive",
    "Android Automotive Developer",
    "Android Engineer, Games Studios",
    "Senior Android Developer (Kotlin)",
    "Senior Mobile Engineer",
])
def test_relevant_titles_pass(title):
    assert is_relevant(title)


@pytest.mark.parametrize("title", [
    "Backend Developer - Android APIs",
    "Android QA - Quality Assurance",
    "Mobile Developer (Flutter)",
    "React Native Developer (Android/iOS)",
    "iOS Developer",
    "Android & iOS Engineer",
])
def test_blacklisted_titles_are_dropped(title):
    assert not is_relevant(title)


def test_title_without_keyword_is_dropped():
    assert not is_relevant("Senior Backend Engineer")


def test_empty_blacklist_blocks_nothing():
    pattern = job_scraper._compile_blacklist([])
    assert pattern.search("android ios studios") is None


def test_salary_missing_values_render_empty():
    assert _format_salary({"min_amount": float("nan"), "max_amount": None}) == ""


def test_salary_with_currency_and_interval():
    row = {"min_amount": 50000.0, "max_amount": 70000.0, "currency": "EUR", "interval": "yearly"}
    assert _format_salary(row) == "50,000 - 70,000 EUR/yearly"


def test_clean_replaces_nan_and_blank():
    assert _clean(float("nan")) == "N/A"
    assert _clean("   ") == "N/A"
    assert _clean(None, default="") == ""
    assert _clean("Munich, BY, DE") == "Munich, BY, DE"
