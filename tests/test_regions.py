"""
Population classification of GWAS sample descriptions (core.regions).
"""

import pytest

from core.regions import ancestry_groups, ancestry_label, is_arab, is_middle_eastern, parse_sample_groups


@pytest.mark.parametrize("text", [
    "2,165 Saudi Arab ancestry cases", "1,200 Qatari individuals", "Lebanese cases", "Emirati adults",
    "Kuwaiti children", "Moroccan ancestry controls", "Egyptian patients", "Arab ancestry", "Tunisian",
    "individuals from Qatar", "participants from Kuwait", "Omani families",
])
def test_arab_samples_are_detected(text):
    assert is_arab(text)
    assert is_middle_eastern(text)


@pytest.mark.parametrize("text", [
    "1,000 European ancestry women", "500 women and 400 men", "Japanese ancestry", "Romanian cases",
    "African American individuals", "Ashkenazi Jewish", "Germans", "Arabidopsis",
])
def test_non_arab_samples_are_not_flagged(text):
    assert not is_arab(text)


@pytest.mark.parametrize("text", ["Iranian ancestry cases", "Turkish controls", "Middle Eastern ancestry",
                                  "Persian individuals"])
def test_non_arab_middle_east(text):
    assert is_middle_eastern(text)
    assert not is_arab(text)


def test_ancestry_label_lists_groups_in_order():
    label = ancestry_label("13,100 European ancestry cases, 2,165 Saudi Arab ancestry cases, 300 Han Chinese")
    assert label == "Arab; European; East Asian"
    assert ancestry_label("") == "Not reported"
    assert ancestry_groups("1,000 African American and 2,000 Nigerian") == ["African American", "African"]


def test_parse_sample_groups_counts_people_not_ages():
    groups = parse_sample_groups("2,165 Saudi Arab ancestry cases, 2,266 Saudi Arab ancestry controls, "
                                 "12,345 European ancestry individuals aged 40 years")
    assert [g.count for g in groups] == [2165, 2266, 12345]
    assert groups[0].groups == ("Arab",)
    assert groups[2].groups == ("European",)


@pytest.mark.parametrize("text, arab", [
    ("11 Arabic ancestry individuals", True), ("65 Saudis ancestry cases", True), ("85 Maghrebian cases", True),
    ("746 North African ancestry individuals", True), ("8 Middle-Eastern ancestry cases", False),
    ("1,170 Israeli ancestry individuals", False), ("155 Jewish-Israeli ancestry cases", False),
])
def test_v2_validation_errors_are_fixed(text, arab):
    """Misses found in validation sample A (docs/research/02_classifier_validation.md)."""
    assert is_middle_eastern(text)
    assert is_arab(text) is arab
