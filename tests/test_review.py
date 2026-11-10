from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from scripts import cv
from tests.conftest import save_yaml


def mark_approved(review_path: Path, *, acknowledged: bool = True) -> None:
    review = cv.load_yaml(review_path)
    review["decision"] = "approved"
    review["reviewer"] = "human via chat"
    review["reviewed_at"] = "2026-11-10T10:30:00+07:00"
    review["acknowledge_exclusions"] = acknowledged
    save_yaml(review_path, review)


def test_new_intake_human_gate_full_happy_path(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    assert not cv.PROFILE.exists()
    review = cv.load_yaml(cv.REVIEW)
    assert review["decision"] == "pending"
    assert review["profile_snapshot"] == example_profile
    assert review["summary"]["record_counts"]["projects"] == 1
    assert review["draft_sha256"] == cv.path_digest(cv.DRAFT)
    with pytest.raises(cv.CVError, match="decision is not approved"):
        cv.approve()
    mark_approved(cv.REVIEW)
    cv.approve()
    assert cv.load_yaml(cv.PROFILE) == example_profile


def test_pending_review_reuses_same_snapshot(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    cv.prepare_review()  # no reset of an existing same-hash approval
    assert cv.load_yaml(cv.REVIEW)["decision"] == "approved"


def test_changed_draft_invalidates_review(workspace: Path, example_profile: dict[str, Any]) -> None:
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    data = copy.deepcopy(example_profile)
    data["candidate"]["headline"] = "Backend Engineer"
    save_yaml(cv.DRAFT, data)
    with pytest.raises(cv.CVError, match="stale"):
        cv.approve()
    with pytest.raises(cv.CVError, match="stale"):
        cv.prepare_review()
    cv.prepare_review(replace=True)
    assert cv.load_yaml(cv.REVIEW)["decision"] == "pending"


def test_tampered_snapshot_rejected(workspace: Path, example_profile: dict[str, Any]) -> None:
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    review = cv.load_yaml(cv.REVIEW)
    review["profile_snapshot"]["candidate"]["full_name"] = "Unexpected Change"
    save_yaml(cv.REVIEW, review)
    with pytest.raises(cv.CVError, match="snapshot differs"):
        cv.approve()


def test_tampered_summary_rejected(workspace: Path, example_profile: dict[str, Any]) -> None:
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    review = cv.load_yaml(cv.REVIEW)
    review["summary"]["full_name"] = "Wrong Name"
    save_yaml(cv.REVIEW, review)
    with pytest.raises(cv.CVError, match="summary was modified"):
        cv.approve()


@pytest.mark.parametrize("key", ["reviewer", "reviewed_at"])
def test_missing_human_metadata_blocked(
    workspace: Path, example_profile: dict[str, Any], key: str
) -> None:
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    review = cv.load_yaml(cv.REVIEW)
    review[key] = None
    save_yaml(cv.REVIEW, review)
    with pytest.raises(cv.CVError, match=key):
        cv.approve()


def test_unresolved_claims_require_acknowledgment(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    example_profile["projects"][0]["highlights"][0]["verification"] = "inferred"
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    mark_approved(cv.REVIEW, acknowledged=False)
    with pytest.raises(cv.CVError, match="acknowledge"):
        cv.approve()
    mark_approved(cv.REVIEW, acknowledged=True)
    cv.approve()
    assert cv.PROFILE.is_file()


def test_open_questions_require_acknowledgment(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    example_profile["open_questions"] = [{"id": "q1", "question": "Did you deploy it?"}]
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    mark_approved(cv.REVIEW, acknowledged=False)
    with pytest.raises(cv.CVError, match="acknowledge"):
        cv.approve()


def test_safe_update_happy_path_backs_up_old_file(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    cv.approve()
    old_hash = cv.path_digest(cv.PROFILE)
    cv.begin_update()
    draft = cv.load_yaml(cv.DRAFT)
    assert draft["base_profile_sha256"] == old_hash
    draft["candidate"]["headline"] = "New Role"
    save_yaml(cv.DRAFT, draft)
    cv.prepare_review(replace=True)
    mark_approved(cv.REVIEW)
    with pytest.raises(cv.CVError, match="profile exists"):
        cv.approve()
    cv.approve(replace=True)
    assert cv.load_yaml(cv.PROFILE)["candidate"]["headline"] == "New Role"
    backup_files = list((cv.DATA / "history").glob("profile-*.yaml"))
    assert len(backup_files) == 1
    assert cv.path_digest(backup_files[0]) == old_hash


def test_update_concurrency_detects_change(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    save_yaml(cv.PROFILE, example_profile)
    save_yaml(cv.PREFERENCES, cv.default_preferences())
    cv.PREFERENCES_DRAFT.unlink()
    cv.begin_update()
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    altered = copy.deepcopy(example_profile)
    altered["candidate"]["headline"] = "Other writer"
    save_yaml(cv.PROFILE, altered)
    with pytest.raises(cv.CVError, match="changed since draft"):
        cv.approve(replace=True)


def test_begin_update_does_not_overwrite_draft(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    save_yaml(cv.PROFILE, example_profile)
    save_yaml(cv.DRAFT, example_profile)
    with pytest.raises(cv.CVError, match="already exists"):
        cv.begin_update()


def test_begin_update_requires_profile(workspace: Path) -> None:
    with pytest.raises(cv.CVError, match="No approved profile"):
        cv.begin_update()


def test_new_approval_rejects_baseline_without_previous_profile(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    example_profile["base_profile_sha256"] = "a" * 64
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    with pytest.raises(cv.CVError, match="expects an existing"):
        cv.approve()
