from eligibility import ELIGIBLE, INELIGIBLE, MAYBE, Eligibility
from ranking import score

ELIGIBLE_EU = Eligibility(ELIGIBLE, "UE")


def test_niche_senior_eligible_with_stack_gets_top_score():
    job = {"title": "Senior Android Automotive Engineer", "description": "AAOS, VHAL, Kotlin"}
    assert score(job, ELIGIBLE_EU) == 10


def test_generic_android_scores_below_niche():
    niche = {"title": "Senior Android Automotive Engineer", "description": ""}
    generic = {"title": "Senior Android Engineer", "description": ""}
    assert score(niche, ELIGIBLE_EU) > score(generic, ELIGIBLE_EU)


def test_junior_language_and_repost_are_penalized():
    base = {"title": "Android Developer", "description": ""}
    assert score({**base, "title": "Junior Android Developer"}, ELIGIBLE_EU) < score(base, ELIGIBLE_EU)
    assert score(base, Eligibility(ELIGIBLE, "UE", ("german",))) < score(base, ELIGIBLE_EU)
    assert score({**base, "repost_of": "2026-09-01"}, ELIGIBLE_EU) < score(base, ELIGIBLE_EU)


def test_eligibility_order_and_bounds():
    job = {"title": "Android Developer", "description": ""}
    assert score(job, ELIGIBLE_EU) > score(job, Eligibility(MAYBE, "?")) > score(job, Eligibility(INELIGIBLE, "x"))
    assert score({"title": "Junior Intern", "description": ""}, Eligibility(INELIGIBLE, "x", ("german",))) == 0
