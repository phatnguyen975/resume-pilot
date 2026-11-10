"""Failure-path tests for preserving human-reviewed data."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from scripts import cv
from tests.conftest import save_yaml
from tests.test_review import mark_approved


def reviewed_draft(profile: dict[str, Any]) -> None:
    save_yaml(cv.DRAFT, profile)
    cv.prepare_review()
    mark_approved(cv.REVIEW)


def test_review_requires_explicit_preference_draft(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    save_yaml(cv.DRAFT, example_profile)
    cv.PREFERENCES_DRAFT.unlink()
    with pytest.raises(cv.CVError, match="Ask the human"):
        cv.prepare_review()
    assert not cv.PREFERENCES_DRAFT.exists()
    assert not cv.REVIEW.exists()


def test_reusing_review_checks_snapshot_integrity(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    reviewed_draft(example_profile)
    review = cv.load_yaml(cv.REVIEW)
    review["preferences_snapshot"]["resume"]["target_pages"] = 3
    save_yaml(cv.REVIEW, review)
    with pytest.raises(cv.CVError, match="snapshot"):
        cv.prepare_review()


@pytest.mark.parametrize("existing", [False, True])
def test_promotion_restores_both_files_after_second_write_failure(
    workspace: Path,
    example_profile: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    existing: bool,
) -> None:
    reviewed_draft(example_profile)
    if existing:
        cv.approve()
        cv.begin_update()
        draft = cv.load_yaml(cv.DRAFT)
        draft["candidate"]["headline"] = "Updated Analyst"
        save_yaml(cv.DRAFT, draft)
        cv.prepare_review()
        mark_approved(cv.REVIEW)
    originals = {p: p.read_bytes() if p.exists() else None for p in (cv.PROFILE, cv.PREFERENCES)}
    write = cv.write_yaml_atomic

    def fail_preferences(path: Path, data: Any) -> None:
        if path == cv.PREFERENCES:
            raise OSError("disk full")
        write(path, data)

    monkeypatch.setattr(cv, "write_yaml_atomic", fail_preferences)
    with pytest.raises(cv.CVError, match="previous files restored"):
        cv.approve(replace=existing)
    for path, content in originals.items():
        assert (path.read_bytes() if path.exists() else None) == content
    assert cv.DRAFT.exists() and cv.PREFERENCES_DRAFT.exists() and cv.REVIEW.exists()


def test_archive_copy_failure_does_not_promote_or_delete_drafts(
    workspace: Path, example_profile: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    reviewed_draft(example_profile)
    original_copy = cv.shutil.copy2

    def fail_review_copy(source: Path, target: Path) -> Any:
        if source == cv.REVIEW:
            raise OSError("archive unavailable")
        return original_copy(source, target)

    monkeypatch.setattr(cv.shutil, "copy2", fail_review_copy)
    with pytest.raises(OSError, match="archive"):
        cv.approve()
    assert not cv.PROFILE.exists() and not cv.PREFERENCES.exists()
    assert all(p.exists() for p in (cv.DRAFT, cv.PREFERENCES_DRAFT, cv.REVIEW))


def test_update_validates_profile_before_writing_preferences(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    reviewed_draft(example_profile)
    cv.approve()
    cv.PROFILE.write_text("candidate: []\n", encoding="utf-8")
    with pytest.raises(cv.CVError):
        cv.begin_update()
    assert not cv.DRAFT.exists() and not cv.PREFERENCES_DRAFT.exists()


def test_update_requires_approved_preferences(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    save_yaml(cv.PROFILE, example_profile)
    cv.PREFERENCES_DRAFT.unlink()
    with pytest.raises(cv.CVError, match="approved data/preferences"):
        cv.begin_update()
    assert not cv.PREFERENCES_DRAFT.exists()


@pytest.mark.parametrize("changed", ["theme", "language", "target_pages"])
def test_each_preference_change_requires_fresh_approval(
    workspace: Path, example_profile: dict[str, Any], changed: str
) -> None:
    reviewed_draft(example_profile)
    prefs = cv.load_yaml(cv.PREFERENCES_DRAFT)
    prefs["resume"][changed] = {"theme": "ink", "language": "vietnamese", "target_pages": 2}[
        changed
    ]
    save_yaml(cv.PREFERENCES_DRAFT, prefs)
    with pytest.raises(cv.CVError, match="preferences changed"):
        cv.approve()
    cv.prepare_review(replace=True)
    assert cv.load_yaml(cv.REVIEW)["decision"] == "pending"
    with pytest.raises(cv.CVError, match="decision"):
        cv.approve()


def test_preferences_concurrency_preserves_newer_approved_data(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    reviewed_draft(example_profile)
    cv.approve()
    cv.begin_update()
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    prefs = cv.load_yaml(cv.PREFERENCES)
    prefs["resume"]["theme"] = "opal"
    save_yaml(cv.PREFERENCES, prefs)
    digest = cv.path_digest(cv.PREFERENCES)
    with pytest.raises(cv.CVError, match="preferences changed since"):
        cv.approve(replace=True)
    assert cv.path_digest(cv.PREFERENCES) == digest


def test_unknown_preferences_baseline_is_not_an_initial_approval(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    prefs = cv.load_yaml(cv.PREFERENCES_DRAFT)
    prefs["base_preferences_sha256"] = "b" * 64
    save_yaml(cv.PREFERENCES_DRAFT, prefs)
    reviewed_draft(example_profile)
    with pytest.raises(cv.CVError, match=r"preferences.*missing"):
        cv.approve()


def test_update_missing_original_profile_is_rejected(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    reviewed_draft(example_profile)
    cv.approve()
    cv.begin_update()
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    cv.PROFILE.unlink()
    with pytest.raises(cv.CVError, match="expects an existing approved profile"):
        cv.approve(replace=True)


def test_present_start_date_is_not_a_calendar_start(example_profile: dict[str, Any]) -> None:
    profile = copy.deepcopy(example_profile)
    profile["experience"][0]["start_date"] = "present"
    with pytest.raises(cv.CVError, match="Start date"):
        cv.validate_profile(profile)


@pytest.mark.parametrize("date", ["2024-1", "2024-01-01-01", "", "not-a-date"])
def test_date_parser_rejects_malformed_dates(date: str) -> None:
    with pytest.raises(cv.CVError, match="calendar date"):
        cv.date_bounds(date)


@pytest.mark.parametrize("text", ["1: value\n", "? [a, b]\n: value\n"])
def test_yaml_rejects_nonstring_mapping_keys(workspace: Path, text: str) -> None:
    path = workspace / "invalid.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(cv.CVError, match="keys must be strings"):
        cv.load_yaml(path)


def test_unrecoverable_write_reports_recovery_failure(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = workspace / "first.yaml", workspace / "second.yaml"
    first.write_text("old: true\n", encoding="utf-8")
    second.write_text("old: true\n", encoding="utf-8")

    def fail(*args: Any) -> None:
        raise OSError("device unavailable")

    monkeypatch.setattr(cv, "write_atomic", fail)
    with pytest.raises(cv.CVError, match="Write and recovery failed"):
        cv.write_yaml_pair(first, {"new": True}, second, {"new": True})


def test_invalid_review_version_cannot_use_boolean_as_integer(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    reviewed_draft(example_profile)
    review = cv.load_yaml(cv.REVIEW)
    review["schema_version"] = True
    with pytest.raises(cv.CVError, match="structure/version"):
        cv.validate_review(review, cv.DRAFT)


@pytest.mark.parametrize("changed", ["profile", "preferences"])
def test_draft_changed_during_approval_cannot_be_promoted(
    workspace: Path,
    example_profile: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    changed: str,
) -> None:
    reviewed_draft(example_profile)
    validate = cv.validate_review

    def change_after_validation(review: Any, draft: Path) -> dict[str, Any]:
        result = validate(review, draft)
        if changed == "profile":
            payload = cv.load_yaml(cv.DRAFT)
            payload["candidate"]["headline"] = "Unreviewed title"
            save_yaml(cv.DRAFT, payload)
        else:
            payload = cv.load_yaml(cv.PREFERENCES_DRAFT)
            payload["resume"]["theme"] = "opal"
            save_yaml(cv.PREFERENCES_DRAFT, payload)
        return result

    monkeypatch.setattr(cv, "validate_review", change_after_validation)
    with pytest.raises(cv.CVError, match="changed during approval"):
        cv.approve()
    assert not cv.PROFILE.exists() and not cv.PREFERENCES.exists()
    assert cv.DRAFT.exists() and cv.REVIEW.exists()
