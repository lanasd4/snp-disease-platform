"""
Knowledge library and community discussions.

Library items are reviewed by an admin before anyone sees them. Community posts
are visible at once but are always presented as users' opinions, never as
platform evidence; votes measure user agreement only and are kept apart from the
research-based evidence level.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.references import ReferenceCheck, check_reference
from core.userdb import connect, id_column_sql

ITEM_TYPES = ("paper", "dataset", "explanation", "protocol")
LIBRARY_PENDING, LIBRARY_PUBLISHED, LIBRARY_REJECTED = "pending", "published", "rejected"
VISIBLE, HIDDEN = "visible", "hidden"

TITLE_MAX, BODY_MAX, COMMENT_MAX, URL_MAX = 200, 5000, 2000, 500
POSTS_PER_HOUR = 5
COMMENTS_PER_HOUR = 30

# Personal genetic results are not allowed in public posts.
PERSONAL_GENOTYPE_RE = re.compile(
    r"\b(my|mine|i have|i carry|my (son|daughter|child|mother|father|wife|husband)('s)?)\b[^.\n]{0,60}"
    r"\b(rs\d+|genotype|23andme|ancestrydna|test result)\b"
    r"|(نتيجتي|تحليلي|الجينوم تبعي|عندي الطفرة|عندي المتغير)",
    re.IGNORECASE,
)


class CommunityError(ValueError):
    """Raised for user input the platform refuses (shown to the user as-is)."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_schema_ready: set = set()


def ensure_schema() -> None:
    """Create the tables if missing.

    The SQLite file can be swapped for the repository copy while the app keeps
    running (hosting pulls a new commit), so for SQLite the cheap CREATE IF NOT
    EXISTS check runs every time; only the remote Postgres check is cached.
    """
    from core.userdb import database_url

    url = database_url()
    if url and url in _schema_ready:
        return
    _ensure_schema()
    if url:
        _schema_ready.add(url)


def _ensure_schema() -> None:
    with connect() as conn:
        pk = id_column_sql(conn.dialect)
        statements = [
            f"""CREATE TABLE IF NOT EXISTS LibraryItem (
                id {pk}, item_type TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
                url TEXT, reference_id TEXT, disease TEXT, gene TEXT,
                submitted_by TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                review_note TEXT, reviewed_by TEXT, reviewed_at TEXT,
                ref_status TEXT, ref_details TEXT, created_at TEXT NOT NULL)""",
            f"""CREATE TABLE IF NOT EXISTS CommunityPost (
                id {pk}, title TEXT NOT NULL, body TEXT NOT NULL, disease TEXT, gene TEXT,
                reference_id TEXT, ref_status TEXT, ref_details TEXT,
                author TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'visible', created_at TEXT NOT NULL)""",
            f"""CREATE TABLE IF NOT EXISTS CommunityComment (
                id {pk}, post_id INTEGER NOT NULL, body TEXT NOT NULL, author TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'visible', created_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS CommunityVote (
                target_type TEXT NOT NULL, target_id INTEGER NOT NULL, username TEXT NOT NULL,
                value INTEGER NOT NULL CHECK (value IN (-1, 1)), created_at TEXT NOT NULL,
                PRIMARY KEY (target_type, target_id, username))""",
            f"""CREATE TABLE IF NOT EXISTS CommunityReport (
                id {pk}, target_type TEXT NOT NULL, target_id INTEGER NOT NULL, reason TEXT NOT NULL,
                reporter TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
                resolved_by TEXT, created_at TEXT NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_library_status ON LibraryItem (status)",
            "CREATE INDEX IF NOT EXISTS idx_comment_post ON CommunityComment (post_id)",
        ]
        for sql in statements:
            conn.execute(sql)


# --- validation -------------------------------------------------------------------

def _clean(text: Optional[str], limit: int, field: str, required: bool = True) -> str:
    value = (text or "").strip()
    if required and not value:
        raise CommunityError(f"{field} is required.")
    if len(value) > limit:
        raise CommunityError(f"{field} is too long (max {limit} characters).")
    return value


def _check_url(url: str) -> str:
    url = _clean(url, URL_MAX, "Link", required=False)
    if url and not re.match(r"^https?://[^\s]+$", url, re.IGNORECASE):
        raise CommunityError("Links must start with http:// or https://.")
    return url


def _reject_personal_data(*texts: str) -> None:
    if any(PERSONAL_GENOTYPE_RE.search(t or "") for t in texts):
        raise CommunityError("Please don't share personal genetic results. Discuss findings in general terms.")


def _rate_limit(conn, table: str, author: str, limit: int) -> None:
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat()
    row = conn.fetch_one(f"SELECT COUNT(*) AS n FROM {table} WHERE author = ? AND created_at >= ?", (author, since))
    if row and row["n"] >= limit:
        raise CommunityError("You are posting too quickly. Please try again later.")


def _reference(reference_id: str, title: str) -> tuple[str, Optional[str], Optional[str], Optional[ReferenceCheck]]:
    reference_id = (reference_id or "").strip()
    if not reference_id:
        return "", None, None, None
    check = check_reference(reference_id, title)
    return reference_id, check.status, json.dumps(check.to_dict()), check


def ref_details(row: dict) -> dict:
    try:
        return json.loads(row.get("ref_details") or "{}")
    except ValueError:
        return {}


# --- library ----------------------------------------------------------------------

def submit_library_item(username: str, item_type: str, title: str, description: str, url: str = "",
                        reference_id: str = "", disease: str = "", gene: str = "") -> int:
    if not username:
        raise CommunityError("Please sign in to submit.")
    if item_type not in ITEM_TYPES:
        raise CommunityError("Unknown material type.")
    title = _clean(title, TITLE_MAX, "Title")
    description = _clean(description, BODY_MAX, "Description")
    url = _check_url(url)
    if item_type == "paper" and not reference_id.strip():
        raise CommunityError("Papers need a PubMed ID or DOI (we link to papers instead of hosting them).")
    if not (url or reference_id.strip()):
        raise CommunityError("Add a link or a PubMed ID / DOI.")
    _reject_personal_data(title, description)
    reference_id, ref_status, details, _ = _reference(reference_id, title if item_type == "paper" else "")
    ensure_schema()
    with connect() as conn:
        row = conn.fetch_one(
            "SELECT COUNT(*) AS n FROM LibraryItem WHERE submitted_by = ? AND status = 'pending'", (username,))
        if row and row["n"] >= 10:
            raise CommunityError("You already have 10 submissions waiting for review.")
        return conn.insert(
            "INSERT INTO LibraryItem (item_type, title, description, url, reference_id, disease, gene, "
            "submitted_by, status, ref_status, ref_details, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (item_type, title, description, url, reference_id, disease.strip(), gene.strip().upper(),
             username, LIBRARY_PENDING, ref_status, details, _now()),
        )


def list_library(status: str = LIBRARY_PUBLISHED, item_type: str = "", disease: str = "", query: str = "",
                 submitted_by: str = "") -> list[dict]:
    ensure_schema()
    sql = "SELECT * FROM LibraryItem WHERE status = ?"
    params: list = [status]
    if item_type:
        sql += " AND item_type = ?"
        params.append(item_type)
    if disease:
        sql += " AND disease = ?"
        params.append(disease)
    if submitted_by:
        sql += " AND submitted_by = ?"
        params.append(submitted_by)
    if query.strip():
        sql += " AND (LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR LOWER(gene) LIKE ?)"
        like = f"%{query.strip().lower()}%"
        params += [like, like, like]
    sql += " ORDER BY created_at DESC"
    with connect() as conn:
        return conn.fetch_all(sql, params)


def review_library_item(item_id: int, approve: bool, admin: str, note: str = "") -> None:
    note = _clean(note, 500, "Note", required=not approve)
    ensure_schema()
    with connect() as conn:
        conn.execute(
            "UPDATE LibraryItem SET status = ?, review_note = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?",
            (LIBRARY_PUBLISHED if approve else LIBRARY_REJECTED, note, admin, _now(), item_id),
        )


def recheck_library_reference(item_id: int) -> Optional[str]:
    ensure_schema()
    with connect() as conn:
        row = conn.fetch_one("SELECT * FROM LibraryItem WHERE id = ?", (item_id,))
        if not row or not row.get("reference_id"):
            return None
        title = row["title"] if row["item_type"] == "paper" else ""
        _, status, details, _ = _reference(row["reference_id"], title)
        conn.execute("UPDATE LibraryItem SET ref_status = ?, ref_details = ? WHERE id = ?", (status, details, item_id))
        return status


# --- community --------------------------------------------------------------------

def create_post(username: str, title: str, body: str, disease: str = "", gene: str = "",
                reference_id: str = "") -> int:
    if not username:
        raise CommunityError("Please sign in to post.")
    title = _clean(title, TITLE_MAX, "Title")
    body = _clean(body, BODY_MAX, "Text")
    _reject_personal_data(title, body)
    reference_id, ref_status, details, _ = _reference(reference_id, "")
    ensure_schema()
    with connect() as conn:
        _rate_limit(conn, "CommunityPost", username, POSTS_PER_HOUR)
        return conn.insert(
            "INSERT INTO CommunityPost (title, body, disease, gene, reference_id, ref_status, ref_details, "
            "author, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (title, body, disease.strip(), gene.strip().upper(), reference_id, ref_status, details,
             username, VISIBLE, _now()),
        )


def add_comment(username: str, post_id: int, body: str) -> int:
    if not username:
        raise CommunityError("Please sign in to comment.")
    body = _clean(body, COMMENT_MAX, "Comment")
    _reject_personal_data(body)
    ensure_schema()
    with connect() as conn:
        if not conn.fetch_one("SELECT id FROM CommunityPost WHERE id = ? AND status = 'visible'", (post_id,)):
            raise CommunityError("This post is no longer available.")
        _rate_limit(conn, "CommunityComment", username, COMMENTS_PER_HOUR)
        return conn.insert(
            "INSERT INTO CommunityComment (post_id, body, author, status, created_at) VALUES (?,?,?,?,?)",
            (post_id, body, username, VISIBLE, _now()),
        )


def vote(username: str, target_type: str, target_id: int, value: int) -> None:
    """Up (+1) or down (-1); voting the same way again removes the vote."""
    if not username:
        raise CommunityError("Please sign in to vote.")
    if target_type not in ("post", "comment") or value not in (-1, 1):
        raise CommunityError("Invalid vote.")
    ensure_schema()
    with connect() as conn:
        current = conn.fetch_one(
            "SELECT value FROM CommunityVote WHERE target_type = ? AND target_id = ? AND username = ?",
            (target_type, target_id, username))
        if current and current["value"] == value:
            conn.execute("DELETE FROM CommunityVote WHERE target_type = ? AND target_id = ? AND username = ?",
                         (target_type, target_id, username))
            return
        conn.execute(
            "INSERT INTO CommunityVote (target_type, target_id, username, value, created_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT (target_type, target_id, username) DO UPDATE SET value = excluded.value",
            (target_type, target_id, username, value, _now()))


def _scores(conn, target_type: str, ids: list[int], username: str) -> dict:
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = conn.fetch_all(
        f"SELECT target_id, SUM(CASE WHEN value > 0 THEN 1 ELSE 0 END) AS up, "
        f"SUM(CASE WHEN value < 0 THEN 1 ELSE 0 END) AS down FROM CommunityVote "
        f"WHERE target_type = ? AND target_id IN ({marks}) GROUP BY target_id", [target_type, *ids])
    scores = {int(r["target_id"]): {"up": int(r["up"] or 0), "down": int(r["down"] or 0), "mine": 0} for r in rows}
    if username:
        for r in conn.fetch_all(
                f"SELECT target_id, value FROM CommunityVote WHERE target_type = ? AND username = ? "
                f"AND target_id IN ({marks})", [target_type, username, *ids]):
            scores.setdefault(int(r["target_id"]), {"up": 0, "down": 0, "mine": 0})["mine"] = int(r["value"])
    return scores


def list_posts(username: str = "", disease: str = "", sort: str = "new", include_hidden: bool = False) -> list[dict]:
    ensure_schema()
    sql = "SELECT * FROM CommunityPost WHERE 1 = 1"
    params: list = []
    if not include_hidden:
        sql += " AND status = 'visible'"
    if disease:
        sql += " AND disease = ?"
        params.append(disease)
    sql += " ORDER BY created_at DESC"
    with connect() as conn:
        posts = conn.fetch_all(sql, params)
        ids = [int(p["id"]) for p in posts]
        scores = _scores(conn, "post", ids, username)
        counts = {}
        if ids:
            marks = ",".join("?" * len(ids))
            counts = {int(r["post_id"]): int(r["n"]) for r in conn.fetch_all(
                f"SELECT post_id, COUNT(*) AS n FROM CommunityComment WHERE status = 'visible' "
                f"AND post_id IN ({marks}) GROUP BY post_id", ids)}
    for p in posts:
        s = scores.get(int(p["id"]), {"up": 0, "down": 0, "mine": 0})
        p.update(up=s["up"], down=s["down"], my_vote=s["mine"], comments=counts.get(int(p["id"]), 0))
    if sort == "top":
        posts.sort(key=lambda p: (p["up"] - p["down"], p["created_at"]), reverse=True)
    return posts


def list_comments(post_id: int, username: str = "") -> list[dict]:
    ensure_schema()
    with connect() as conn:
        comments = conn.fetch_all(
            "SELECT * FROM CommunityComment WHERE post_id = ? AND status = 'visible' ORDER BY created_at", (post_id,))
        scores = _scores(conn, "comment", [int(c["id"]) for c in comments], username)
    for c in comments:
        s = scores.get(int(c["id"]), {"up": 0, "down": 0, "mine": 0})
        c.update(up=s["up"], down=s["down"], my_vote=s["mine"])
    return comments


def report(username: str, target_type: str, target_id: int, reason: str) -> int:
    if not username:
        raise CommunityError("Please sign in to report.")
    if target_type not in ("post", "comment", "library"):
        raise CommunityError("Invalid report.")
    reason = _clean(reason, 500, "Reason")
    ensure_schema()
    with connect() as conn:
        return conn.insert(
            "INSERT INTO CommunityReport (target_type, target_id, reason, reporter, status, created_at) "
            "VALUES (?,?,?,?,?,?)", (target_type, target_id, reason, username, "open", _now()))


def list_reports(status: str = "open") -> list[dict]:
    ensure_schema()
    with connect() as conn:
        return conn.fetch_all("SELECT * FROM CommunityReport WHERE status = ? ORDER BY created_at DESC", (status,))


def get_target_text(target_type: str, target_id: int) -> str:
    table = {"post": "CommunityPost", "comment": "CommunityComment", "library": "LibraryItem"}[target_type]
    column = "title" if target_type in ("post", "library") else "body"
    ensure_schema()
    with connect() as conn:
        row = conn.fetch_one(f"SELECT {column} AS text FROM {table} WHERE id = ?", (target_id,))
    return (row or {}).get("text", "")


def resolve_report(report_id: int, admin: str, hide_content: bool) -> None:
    ensure_schema()
    with connect() as conn:
        row = conn.fetch_one("SELECT * FROM CommunityReport WHERE id = ?", (report_id,))
        if not row:
            return
        if hide_content:
            set_hidden(row["target_type"], int(row["target_id"]), True, conn=conn)
        conn.execute("UPDATE CommunityReport SET status = 'resolved', resolved_by = ? WHERE id = ?",
                     (admin, report_id))


def set_hidden(target_type: str, target_id: int, hidden: bool, conn=None) -> None:
    if target_type == "library":
        sql = "UPDATE LibraryItem SET status = ? WHERE id = ?"
        value = LIBRARY_REJECTED if hidden else LIBRARY_PUBLISHED
    else:
        table = "CommunityPost" if target_type == "post" else "CommunityComment"
        sql = f"UPDATE {table} SET status = ? WHERE id = ?"
        value = HIDDEN if hidden else VISIBLE
    if conn is not None:
        conn.execute(sql, (value, target_id))
        return
    ensure_schema()
    with connect() as c:
        c.execute(sql, (value, target_id))
