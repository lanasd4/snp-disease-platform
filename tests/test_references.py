"""
Reference checker (core.references) with the registries replaced by fakes.
"""

import pytest
import requests

from core import references as ref

PUBMED = {
    "result": {
        "17463246": {
            "title": "A genome-wide association study identifies novel risk loci for type 2 diabetes.",
            "fulljournalname": "Nature", "pubdate": "2007 Feb 22", "pubtype": ["Journal Article"],
            "articleids": [{"idtype": "doi", "value": "10.1038/nature05616"}],
        },
        "11111": {"title": "Fabricated results", "pubtype": ["Journal Article", "Retracted Publication"],
                  "articleids": []},
        "99999999": {"error": "cannot get document summary"},
    }
}
CROSSREF = {
    "10.1038/nature05616": {"title": ["A genome-wide association study identifies novel risk loci for type 2 diabetes"],
                            "container-title": ["Nature"], "issued": {"date-parts": [[2007, 2, 22]]}},
    "10.1000/retracted": {"title": ["Bad paper"], "updated-by": [{"type": "retraction", "DOI": "10.1000/notice"}]},
    "10.1000/late": {"title": ["Late retraction"]},
}


def fake_fetch(url, params=None):
    if "esummary" in url:
        return {"result": {params["id"]: PUBMED["result"].get(params["id"], {"error": "x"})}}
    if params and "filter" in params:
        doi = params["filter"].split(":", 1)[1]
        items = [{"update-to": [{"type": "retraction", "DOI": "10.1000/late"}]}] if doi == "10.1000/late" else []
        return {"message": {"items": items}}
    doi = url.rsplit("/works/", 1)[1]
    return {"message": CROSSREF[doi]} if doi in CROSSREF else None


@pytest.mark.parametrize("text, expected", [
    ("17463246", ("pmid", "17463246")), ("PMID: 17463246", ("pmid", "17463246")),
    ("https://pubmed.ncbi.nlm.nih.gov/17463246/", ("pmid", "17463246")),
    ("10.1038/NATURE05616", ("doi", "10.1038/nature05616")),
    ("https://doi.org/10.1038/nature05616.", ("doi", "10.1038/nature05616")),
    ("hello", ("", "")), ("", ("", "")),
])
def test_parse_identifier(text, expected):
    assert ref.parse_identifier(text) == expected


def test_valid_pmid_with_matching_title():
    check = ref.check_reference("17463246", "A genome-wide association study identifies novel risk loci for type 2 "
                                "diabetes", fetch=fake_fetch)
    assert check.status == ref.VERIFIED and check.ok
    assert check.journal == "Nature" and check.year == "2007" and check.doi == "10.1038/nature05616"


def test_title_mismatch_is_flagged():
    check = ref.check_reference("17463246", "Coffee drinking and happiness", fetch=fake_fetch)
    assert check.status == ref.TITLE_MISMATCH


def test_unknown_ids_are_not_found():
    assert ref.check_reference("99999999", fetch=fake_fetch).status == ref.NOT_FOUND
    assert ref.check_reference("10.1000/nothing", fetch=fake_fetch).status == ref.NOT_FOUND


def test_retractions_are_detected():
    assert ref.check_reference("11111", fetch=fake_fetch).status == ref.RETRACTED
    assert ref.check_reference("10.1000/retracted", fetch=fake_fetch).status == ref.RETRACTED
    assert ref.check_reference("10.1000/late", fetch=fake_fetch).status == ref.RETRACTED


def test_doi_with_markup_title_matches():
    check = ref.check_reference("10.1038/nature05616", "A genome-wide association study identifies novel risk "
                                "loci for type 2 diabetes.", fetch=fake_fetch)
    assert check.status == ref.VERIFIED


def test_invalid_and_unreachable():
    assert ref.check_reference("not an id", fetch=fake_fetch).status == ref.INVALID

    def down(url, params=None):
        raise requests.ConnectionError("offline")

    assert ref.check_reference("17463246", fetch=down).status == ref.UNREACHABLE
