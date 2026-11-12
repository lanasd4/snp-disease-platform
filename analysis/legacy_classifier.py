"""
Frozen copy of the platform's ORIGINAL Arab / Middle East detector
(pipeline/entity_linking.detect_arab_related as of commit 1215f8e).
"""

import re

LEGACY_KEYWORDS = [
    "arab", "middle east", "middle eastern",
    "qatar", "qatari",
    "saudi", "kuwait", "kuwaiti",
    "uae", "emirati",
    "jordan", "jordanian",
    "palestine", "palestinian",
    "lebanon", "lebanese",
    "egypt", "egyptian",
    "oman", "omani",
    "bahrain", "iraq", "iraqi",
    "syria", "syrian",
    "morocco", "moroccan",
    "tunisia", "tunisian",
    "algeria", "algerian", "libya", "libyan", "sudan", "sudanese", "yemen", "yemeni",
    "iran", "iranian", "persian", "turkish",
]


def _normalize(text: str) -> str:
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9؀-ۿ]+", " ", text)
    return " ".join(text.split())


def legacy_is_arab_or_middle_east(text: str) -> bool:
    """Plain substring search, exactly as the original pipeline did it."""
    combined = _normalize(text)
    return any(keyword in combined for keyword in LEGACY_KEYWORDS)
