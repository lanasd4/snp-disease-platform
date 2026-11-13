"""
Knowledge library and community rules (core.community) on a throwaway SQLite database.
"""

import shutil

import pytest

import core.community as cm
import core.paths
import core.userdb as userdb
from core.references import ReferenceCheck


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    path = tmp_path / "community.db"
    shutil.copy(core.paths.DATABASE_PATH, path)
    monkeypatch.setattr(userdb, "DATABASE_PATH", path)
    monkeypatch.setattr(core.paths, "DATABASE_PATH", path)
    monkeypatch.delenv("SNP_USER_DB_URL", raising=False)
    cm._schema_ready.clear()
    monkeypatch.setattr(cm, "check_reference", lambda ident, title="": ReferenceCheck("verified", "pmid", ident))
    return path


def test_library_item_needs_review_before_it_is_public():
    item_id = cm.submit_library_item("lana", "paper", "TCF7L2 and T2D", "Key GWAS paper", reference_id="17463246")
    assert cm.list_library() == []
    assert cm.list_library(status=cm.LIBRARY_PENDING)[0]["ref_status"] == "verified"
    cm.review_library_item(item_id, approve=True, admin="admin")
    published = cm.list_library()
    assert [i["id"] for i in published] == [item_id]
    assert cm.list_library(query="tcf7l2")[0]["id"] == item_id


def test_rejection_requires_a_reason():
    item_id = cm.submit_library_item("lana", "dataset", "Data", "Open data", url="https://example.org/data")
    with pytest.raises(cm.CommunityError):
        cm.review_library_item(item_id, approve=False, admin="admin", note="")
    cm.review_library_item(item_id, approve=False, admin="admin", note="Duplicate")
    assert cm.list_library(status=cm.LIBRARY_REJECTED)[0]["review_note"] == "Duplicate"


@pytest.mark.parametrize("kwargs", [
    dict(item_type="paper", title="x", description="y"),  # paper without PMID/DOI
    dict(item_type="explanation", title="x", description="y"),  # no link at all
    dict(item_type="explanation", title="x", description="y", url="javascript:alert(1)"),
    dict(item_type="video", title="x", description="y", url="https://e.org"),
    dict(item_type="explanation", title="", description="y", url="https://e.org"),
])
def test_invalid_library_submissions(kwargs):
    with pytest.raises(cm.CommunityError):
        cm.submit_library_item("lana", **kwargs)


def test_guests_cannot_submit_post_or_vote():
    with pytest.raises(cm.CommunityError):
        cm.submit_library_item("", "explanation", "t", "d", url="https://e.org")
    with pytest.raises(cm.CommunityError):
        cm.create_post("", "t", "b")
    with pytest.raises(cm.CommunityError):
        cm.vote("", "post", 1, 1)


def test_posts_comments_and_votes():
    post_id = cm.create_post("lana", "Is TCF7L2 the strongest T2D locus?", "Thoughts?", disease="Type 2 Diabetes")
    cm.add_comment("sami", post_id, "In Europeans yes.")
    cm.vote("sami", "post", post_id, 1)
    cm.vote("rana", "post", post_id, 1)
    cm.vote("omar", "post", post_id, -1)
    post = cm.list_posts(username="sami")[0]
    assert (post["up"], post["down"], post["my_vote"], post["comments"]) == (2, 1, 1, 1)
    cm.vote("sami", "post", post_id, 1)  # same vote again removes it
    cm.vote("omar", "post", post_id, 1)  # changing a vote replaces it
    post = cm.list_posts(username="sami")[0]
    assert (post["up"], post["down"], post["my_vote"]) == (2, 0, 0)
    comment = cm.list_comments(post_id)[0]
    cm.vote("lana", "comment", comment["id"], 1)
    assert cm.list_comments(post_id)[0]["up"] == 1


def test_personal_genetic_data_is_refused():
    with pytest.raises(cm.CommunityError):
        cm.create_post("lana", "Help", "My 23andMe test result shows rs7903146 TT, what should I do?")
    with pytest.raises(cm.CommunityError):
        cm.create_post("lana", "سؤال", "نتيجتي فيها rs7903146")


def test_rate_limit():
    for i in range(cm.POSTS_PER_HOUR):
        cm.create_post("lana", f"Post {i}", "text")
    with pytest.raises(cm.CommunityError):
        cm.create_post("lana", "One more", "text")


def test_report_and_hide():
    post_id = cm.create_post("lana", "Spam", "buy now")
    report_id = cm.report("sami", "post", post_id, "spam")
    assert cm.list_reports()[0]["id"] == report_id
    cm.resolve_report(report_id, admin="admin", hide_content=True)
    assert cm.list_posts() == []
    assert cm.list_reports() == []
    with pytest.raises(cm.CommunityError):
        cm.add_comment("sami", post_id, "late comment")


def test_sql_injection_in_search_is_harmless():
    cm.submit_library_item("lana", "explanation", "Safe", "text", url="https://e.org")
    assert cm.list_library(status=cm.LIBRARY_PENDING, query="' OR 1=1 --") == []
