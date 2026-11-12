from dedupe import fingerprint, normalize_company, normalize_title, split_duplicates


def _job(title, company="ACME GmbH", country="germany", **extra):
    return {"title": title, "company": company, "country": country, **extra}


def test_titles_with_gender_tags_match():
    assert normalize_title("Senior Android Developer (m/w/d)") == "senior android developer"
    assert normalize_title("Senior Android Developer m/f/x") == "senior android developer"
    assert normalize_title("Senior Android-Developer – all genders") == "senior android developer"


def test_company_suffixes_and_accents_are_ignored():
    assert normalize_company("ACME GmbH & Co. KG") == "acme"
    assert normalize_company("Société Générale S.A.") == "societe generale"
    assert normalize_company("Spyrosoft Sp. z o.o.") == "spyrosoft"


def test_same_job_on_two_sites_has_same_fingerprint():
    linkedin = _job("Senior Android Developer (m/w/d)", "ACME GmbH")
    indeed = _job("Senior Android Developer", "ACME")
    assert fingerprint(linkedin) == fingerprint(indeed)


def test_country_separates_fingerprints():
    assert fingerprint(_job("Android Engineer", country="spain")) != fingerprint(_job("Android Engineer", country="poland"))


def test_missing_company_has_no_fingerprint():
    assert fingerprint(_job("Android Engineer", company="N/A")) is None


def test_split_keeps_most_complete_version():
    plain = {"job_url": "li/1", "fingerprint": "acme|android|de", "url_direct": "", "description": ""}
    rich = {"job_url": "in/1", "fingerprint": "acme|android|de", "url_direct": "https://acme.com/1", "description": "x"}
    other = {"job_url": "li/2", "fingerprint": None}

    unique, duplicates = split_duplicates([plain, other, rich])

    assert [j["job_url"] for j in unique] == ["in/1", "li/2"]
    assert [j["job_url"] for j in duplicates] == ["li/1"]
