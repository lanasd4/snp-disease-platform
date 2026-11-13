"""
Automatic reference checking for user-submitted material.

Checks that a PubMed ID or DOI exists, that its title matches the one the user
gave, and that the paper has not been retracted. It does NOT judge whether the
paper supports the user's claim; that stays with the admin and the readers.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Callable, Optional

import requests

PUBMED_SUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
CROSSREF_WORK_URL = "https://api.crossref.org/works/{doi}"
CROSSREF_UPDATES_URL = "https://api.crossref.org/works"
TIMEOUT_S = 8
TITLE_MATCH_THRESHOLD = 0.85
USER_AGENT = "SNP-Disease-Platform reference checker (https://github.com/lanasd4/snp-disease-platform)"

PMID_RE = re.compile(r"^(?:pmid:?\s*)?(\d{1,9})$", re.IGNORECASE)
DOI_RE = re.compile(r"(10\.\d{4,9}/\S+)", re.IGNORECASE)

# Status values, from best to worst.
VERIFIED = "verified"
TITLE_MISMATCH = "title_mismatch"
RETRACTED = "retracted"
NOT_FOUND = "not_found"
INVALID = "invalid"
UNREACHABLE = "unreachable"


@dataclass
class ReferenceCheck:
    status: str
    kind: str = ""  # "pmid" or "doi"
    identifier: str = ""
    found_title: str = ""
    journal: str = ""
    year: str = ""
    doi: str = ""
    title_similarity: Optional[float] = None
    notes: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == VERIFIED

    def to_dict(self) -> dict:
        return asdict(self)


def parse_identifier(text: str) -> tuple[str, str]:
    """Return ("pmid"|"doi", value) or ("", "") when the text is neither."""
    value = (text or "").strip()
    match = PMID_RE.match(value)
    if match:
        return "pmid", match.group(1)
    match = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{1,9})", value)
    if match:
        return "pmid", match.group(1)
    match = DOI_RE.search(value)
    if match:
        return "doi", match.group(1).rstrip(".,;)").lower()
    return "", ""


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKD", title or "").lower()
    text = re.sub(r"<[^>]+>", " ", text)  # Crossref titles may carry markup
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_similarity(a: str, b: str) -> float:
    return round(SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio(), 3)


def _get_json(url: str, params: Optional[dict] = None) -> Optional[dict]:
    response = requests.get(url, params=params, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT})
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _check_pmid(pmid: str, fetch: Callable) -> ReferenceCheck:
    data = fetch(PUBMED_SUMMARY_URL, {"db": "pubmed", "id": pmid, "retmode": "json"})
    record = (data or {}).get("result", {}).get(pmid)
    if not record or record.get("error"):
        return ReferenceCheck(NOT_FOUND, "pmid", pmid, notes=["No PubMed record with this ID."])
    doi = next((a.get("value", "") for a in record.get("articleids", []) if a.get("idtype") == "doi"), "")
    check = ReferenceCheck(
        VERIFIED, "pmid", pmid,
        found_title=record.get("title", "").rstrip("."),
        journal=record.get("fulljournalname") or record.get("source", ""),
        year=str(record.get("pubdate", ""))[:4],
        doi=doi.lower(),
    )
    if "Retracted Publication" in record.get("pubtype", []):
        check.status = RETRACTED
        check.notes.append("PubMed marks this paper as a retracted publication.")
    return check


def _check_doi(doi: str, fetch: Callable) -> ReferenceCheck:
    data = fetch(CROSSREF_WORK_URL.format(doi=doi))
    message = (data or {}).get("message")
    if not message:
        return ReferenceCheck(NOT_FOUND, "doi", doi, notes=["No Crossref record with this DOI."])
    issued = message.get("issued", {}).get("date-parts", [[None]])[0][0]
    check = ReferenceCheck(
        VERIFIED, "doi", doi,
        found_title=(message.get("title") or [""])[0],
        journal=(message.get("container-title") or [""])[0],
        year=str(issued or ""),
        doi=doi,
    )
    retracted = any(u.get("type") == "retraction" for u in message.get("updated-by", []))
    if not retracted:
        notices = fetch(CROSSREF_UPDATES_URL, {"filter": f"updates:{doi}", "rows": 20})
        items = (notices or {}).get("message", {}).get("items", [])
        retracted = any(
            u.get("type") == "retraction" and u.get("DOI", "").lower() == doi
            for item in items for u in item.get("update-to", [])
        )
    if retracted:
        check.status = RETRACTED
        check.notes.append("Crossref lists a retraction notice for this DOI.")
    return check


def check_reference(identifier: str, claimed_title: str = "", fetch: Callable = _get_json) -> ReferenceCheck:
    """Check one PubMed ID or DOI; ``fetch`` is injectable for tests."""
    kind, value = parse_identifier(identifier)
    if not kind:
        return ReferenceCheck(INVALID, notes=["Enter a PubMed ID (digits) or a DOI starting with 10."])
    try:
        check = _check_pmid(value, fetch) if kind == "pmid" else _check_doi(value, fetch)
    except (requests.RequestException, ValueError) as exc:
        return ReferenceCheck(UNREACHABLE, kind, value, notes=[f"Could not reach the registry: {type(exc).__name__}"])
    if check.status == VERIFIED and claimed_title.strip() and check.found_title:
        check.title_similarity = title_similarity(claimed_title, check.found_title)
        if check.title_similarity < TITLE_MATCH_THRESHOLD:
            check.status = TITLE_MISMATCH
            check.notes.append("The title you entered does not match the registered title.")
    return check
