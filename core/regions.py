"""
Population / region classification of GWAS sample descriptions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

# Arab League member states (nationality adjectives and country names).
ARAB_TERMS = [
    r"arab", r"arabic", r"arabian",
    r"saudi", r"saudi arabia", r"emirati", r"uae", r"united arab emirates", r"emirates",
    r"qatar", r"qatari", r"kuwait", r"kuwaiti", r"oman", r"omani", r"bahrain", r"bahraini",
    r"yemen", r"yemeni", r"iraq", r"iraqi", r"syria", r"syrian", r"jordan", r"jordanian",
    r"lebanon", r"lebanese", r"palestine", r"palestinian", r"egypt", r"egyptian",
    r"libya", r"libyan", r"tunisia", r"tunisian", r"algeria", r"algerian",
    r"morocco", r"moroccan", r"sudan", r"sudanese", r"mauritania", r"mauritanian",
    r"djibouti", r"djiboutian", r"comoros", r"comorian", r"somali", r"somalia",
    r"maghreb", r"maghrebi", r"maghrebian", r"north africa", r"north african",
    r"gulf arab", r"bedouin",
]
MIDDLE_EAST_TERMS = [
    r"middle east", r"middle eastern", r"mena", r"near east", r"near eastern",
    r"iran", r"iranian", r"persian", r"turkey", r"turkish", r"kurd", r"kurdish",
    r"israel", r"israeli", r"mizrahi", r"sephardi", r"yemenite",
]


def _terms_regex(terms) -> re.Pattern:
    """Whole words, optional plural "s", and space or hyphen between words ("Middle-Eastern")."""
    parts = [term.replace(" ", r"[\s-]+") + "s?" for term in terms]
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b", re.IGNORECASE)


ARAB_RE = _terms_regex(ARAB_TERMS)
MIDDLE_EAST_RE = _terms_regex(MIDDLE_EAST_TERMS)

# Broad groups for display, in display order. "Arab" and "Middle Eastern" come first.
ANCESTRY_GROUPS: List[Tuple[str, re.Pattern]] = [
    ("Arab", ARAB_RE),
    ("Middle Eastern", MIDDLE_EAST_RE),
    ("European", re.compile(
        r"\b(?:european|white|caucasian|finnish|finn|icelandic|british|english|scottish|irish|dutch|german|"
        r"swedish|danish|norwegian|italian|spanish|french|ashkenazi|sardinian|estonian|polish|greek|"
        r"croatian|hungarian|swiss|austrian|belgian|portuguese|russian|ukrainian|czech)\b", re.I)),
    ("East Asian", re.compile(
        r"\b(?:east asian|japanese|chinese|korean|han|taiwanese|vietnamese|filipino|thai|mongolian|"
        r"malay|indonesian|singaporean)\b", re.I)),
    ("South Asian", re.compile(
        r"\b(?:south asian|indian|pakistani|bangladeshi|sri lankan|nepalese|punjabi|gujarati)\b", re.I)),
    ("African American", re.compile(r"\b(?:african american|african-american|afro-caribbean|black)\b", re.I)),
    ("African", re.compile(
        r"\b(?:african(?![ -]american)|sub-saharan|nigerian|ghanaian|kenyan|ugandan|ethiopian|"
        r"south african|gambian|tanzanian|cameroonian|malawian|yoruba)\b", re.I)),
    ("Hispanic / Latin American", re.compile(
        r"\b(?:hispanic|latin american|latino|latina|mexican|puerto rican|brazilian|peruvian|"
        r"colombian|chilean|admixed american)\b", re.I)),
    ("Other", re.compile(
        r"\b(?:oceanian|native american|american indian|greenlandic|aboriginal|pacific islander|"
        r"polynesian|samoan|native hawaiian|inuit)\b", re.I)),
]

# "<number> <descriptor>" items, e.g. "2,165 Saudi Arab ancestry cases".
SAMPLE_ITEM_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)\s+([^,;]+)")
# Words that turn a number into something other than a head count.
NOT_A_COUNT_RE = re.compile(r"^\s*(?:years?|months?|weeks?|days?|%|percent|families|trios|pedigrees|sibships)\b", re.I)


@dataclass(frozen=True)
class SampleGroup:
    count: int
    text: str
    groups: Tuple[str, ...]


# Umbrella categories that mention North Africa without stating that the
# participants are Arab: they count as Middle Eastern, not as Arab.
MIXED_MENA_RE = re.compile(
    r"greater middle eastern\s*\(middle eastern,\s*north african,?\s*or persian\)|north african jewish",
    re.IGNORECASE,
)


def is_arab(text: str) -> bool:
    return bool(ARAB_RE.search(MIXED_MENA_RE.sub(" ", str(text or ""))))


def is_middle_eastern(text: str) -> bool:
    """Arab, or a non-Arab Middle Eastern population (Iranian, Turkish, ...)."""
    text = str(text or "")
    return bool(ARAB_RE.search(text) or MIDDLE_EAST_RE.search(text))


def ancestry_groups(text: str) -> List[str]:
    """Broad ancestry groups named in a description, in display order."""
    text = str(text or "")
    groups = [name for name, pattern in ANCESTRY_GROUPS
              if (is_arab(text) if name == "Arab" else pattern.search(text))]
    # "Arab" also implies a Middle Eastern sample; avoid listing it twice.
    if "Arab" in groups and "Middle Eastern" in groups and not MIDDLE_EAST_RE.search(ARAB_RE.sub("", text)):
        groups.remove("Middle Eastern")
    return groups


def ancestry_label(text: str) -> str:
    groups = ancestry_groups(text)
    return "; ".join(groups) if groups else "Not reported"


def parse_sample_groups(text: str) -> List[SampleGroup]:
    """Split a sample description into counted groups with their ancestry."""
    items = []
    for raw_count, descriptor in SAMPLE_ITEM_RE.findall(str(text or "")):
        if NOT_A_COUNT_RE.match(descriptor):
            continue
        items.append(SampleGroup(int(raw_count.replace(",", "")), descriptor.strip(),
                                 tuple(ancestry_groups(descriptor))))
    return items
