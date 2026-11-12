"""
Frozen versions of the Arab / Middle Eastern classifier, for the validation
report (docs/research/02_classifier_validation.md). Do not edit: the current
production version lives in core/regions.py.
"""

import re

from analysis.legacy_classifier import legacy_is_arab_or_middle_east
from core.regions import is_arab as v2_is_arab
from core.regions import is_middle_eastern as v2_is_middle_eastern

_V1_ARAB = [
    "arab", "arabs", "arabian", "saudi", "saudi arabia", "emirati", "uae", "united arab emirates",
    "qatar", "qatari", "kuwait", "kuwaiti", "oman", "omani", "bahrain", "bahraini", "yemen", "yemeni",
    "iraq", "iraqi", "syria", "syrian", "jordan", "jordanian", "lebanon", "lebanese", "palestine", "palestinian",
    "egypt", "egyptian", "libya", "libyan", "tunisia", "tunisian", "algeria", "algerian", "morocco", "moroccan",
    "sudan", "sudanese", "mauritania", "mauritanian", "djibouti", "djiboutian", "comoros", "comorian",
    "somali", "somalia", "emirates", "gulf arab", "bedouin",
]
_V1_ME = ["middle east", "middle eastern", "mena", "near east", "near eastern", "iran", "iranian", "persian",
          "turkey", "turkish", "kurd", "kurdish"]
_V1_ARAB_RE = re.compile(r"\b(?:" + "|".join(_V1_ARAB) + r")\b", re.IGNORECASE)
_V1_ME_RE = re.compile(r"\b(?:" + "|".join(_V1_ME) + r")\b", re.IGNORECASE)


def v1_is_arab(text: str) -> bool:
    return bool(_V1_ARAB_RE.search(str(text or "")))


def v1_is_middle_eastern(text: str) -> bool:
    text = str(text or "")
    return bool(_V1_ARAB_RE.search(text) or _V1_ME_RE.search(text))


MIDDLE_EAST_CLASSIFIERS = {
    "legacy": legacy_is_arab_or_middle_east,
    "v1": v1_is_middle_eastern,
    "v2": v2_is_middle_eastern,
}
ARAB_CLASSIFIERS = {
    "v1": v1_is_arab,
    "v2": v2_is_arab,
}
