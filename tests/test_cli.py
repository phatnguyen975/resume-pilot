from __future__ import annotations

import importlib.metadata as metadata
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import cv
from tests.conftest import save_yaml


def test_reexec_rejects_unbootstrapped_project(workspace: Path) -> None:
    with pytest.raises(cv.CVError, match=r"Missing \.venv"):
        cv.reexec_if_needed(["doctor"])
    assert cv.reexec_if_needed(["--help"]) is None


def test_reexec_uses_venv_python(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    interpreter = cv.get_venv_python()
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("fake")
    args_seen: list[str] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        args_seen.extend(argv)
        return subprocess.CompletedProcess(argv, 42)

    monkeypatch.setattr(cv.subprocess, "run", fake_run)
    assert cv.reexec_if_needed(["doctor"]) == 42
    assert args_seen[0] == str(interpreter)
    assert args_seen[-1] == "doctor"


def test_validate_profile_cli_success(workspace: Path, example_profile: dict[str, Any]) -> None:
    save_yaml(cv.DRAFT, example_profile)
    assert cv.main(["validate", "--kind", "profile", "--input", str(cv.DRAFT)]) == 0


def test_validate_invalid_profile_cli_failure(workspace: Path) -> None:
    invalid = workspace / "invalid.yaml"
    invalid.write_text("schema_version: 1\ncandidate: []\n")
    assert cv.main(["validate", "--kind", "profile", "--input", str(invalid)]) == 1


def test_review_cli_then_approve_cli(workspace: Path, example_profile: dict[str, Any]) -> None:
    save_yaml(cv.DRAFT, example_profile)
    assert cv.main(["review"]) == 0
    assert cv.main(["validate", "--kind", "review", "--input", str(cv.REVIEW)]) == 0
    assert cv.main(["approve"]) == 1  # human has not approved yet
    review = cv.load_yaml(cv.REVIEW)
    review["decision"] = "approved"
    review["reviewer"] = "human approval test"
    review["reviewed_at"] = "2026-11-10T10:00:00+07:00"
    save_yaml(cv.REVIEW, review)
    assert cv.main(["approve"]) == 0
    assert cv.PROFILE.is_file()
    assert not cv.DRAFT.exists()
    assert not cv.REVIEW.exists()


def test_review_decision_missing_and_invalid_rejected(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    review = cv.load_yaml(cv.REVIEW)
    del review["decision"]
    save_yaml(cv.REVIEW, review)
    with pytest.raises(cv.CVError, match="missing required key"):
        cv.validate_review(cv.load_yaml(cv.REVIEW), cv.DRAFT)
    review["decision"] = "fake_decision"
    save_yaml(cv.REVIEW, review)
    with pytest.raises(cv.CVError, match="Review decision"):
        cv.validate_review(cv.load_yaml(cv.REVIEW), cv.DRAFT)


def test_date_bounds_rejects_impossible_day() -> None:
    with pytest.raises(cv.CVError, match="Invalid calendar date"):
        cv.date_bounds("2025-02-30")
    assert cv.date_bounds("2025") is not None
    assert cv.date_bounds("present") is None
    start, end = cv.date_bounds("2025-02") or (None, None)
    assert start is not None and start.day == 1
    assert end is not None and end.day == 28


def test_date_bounds_same_year_is_not_false_positive(example_profile: dict[str, Any]) -> None:
    example_profile["education"][0]["start_date"] = "2024-12"
    example_profile["education"][0]["end_date"] = "2024"
    cv.validate_profile(example_profile)


def test_profile_approval_requires_timezone(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    review = cv.load_yaml(cv.REVIEW)
    review.update(
        {"decision": "approved", "reviewer": "human", "reviewed_at": "2026-11-10T12:00:00"}
    )
    save_yaml(cv.REVIEW, review)
    with pytest.raises(cv.CVError, match="timezone"):
        cv.approve()
    review["reviewed_at"] = "not-an-ISO-timestamp"
    save_yaml(cv.REVIEW, review)
    with pytest.raises(cv.CVError, match="ISO-8601"):
        cv.approve()


def test_profile_validation_detects_impossible_date(example_profile: dict[str, Any]) -> None:
    example_profile["projects"][0]["start_date"] = "2025-02-30"
    with pytest.raises(cv.CVError, match="Invalid calendar date"):
        cv.validate_profile(example_profile)


def test_review_schema_version_rejected(workspace: Path, example_profile: dict[str, Any]) -> None:
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    review = cv.load_yaml(cv.REVIEW)
    review["schema_version"] = 2
    with pytest.raises(cv.CVError, match="Invalid intake review"):
        cv.validate_review(review, cv.DRAFT)


def test_rendercv_basic_preflight_does_not_render(workspace: Path) -> None:
    path = workspace / "templates" / "rendercv.example.yaml"
    assert cv.main(["validate", "--kind", "resume", "--input", str(path)]) == 0


def test_doctor_reports_missing_packages(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metadata, "version", lambda name: "missing")
    with pytest.raises(cv.CVError, match="Doctor found problems"):
        cv.doctor()


def test_cli_audit_valid_pdf(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = workspace / "test.pdf"
    pdf.write_bytes(b"pdf handled by fake pdf_report")
    monkeypatch.setattr(
        cv, "pdf_report", lambda path, max_pages=2: {"passed": True, "pages": 1, "warnings": []}
    )
    assert cv.main(["audit", "--pdf", str(pdf)]) == 0
    monkeypatch.setattr(
        cv,
        "pdf_report",
        lambda path, max_pages=2: {"passed": False, "pages": 3, "warnings": ["long"]},
    )
    assert cv.main(["audit", "--pdf", str(pdf)]) == 1


def test_cli_build_requires_approval(workspace: Path) -> None:
    assert (
        cv.main(["build", "--input", str(workspace / "templates" / "rendercv.example.yaml")]) == 1
    )


def test_json_schema_reference_has_correct_version(workspace: Path) -> None:
    text = (workspace / "templates" / "rendercv.example.yaml").read_text()
    assert "refs/tags/v2.8/schema.json" in text
    assert json.loads(cv.SCHEMA.read_text())["properties"]["schema_version"]["const"] == 1


def test_preferences_cli_validation_and_missing_file(workspace: Path) -> None:
    assert cv.main(["validate", "--kind", "preferences", "--input", str(cv.PREFERENCES_DRAFT)]) == 0
    assert (
        cv.main(["validate", "--kind", "profile", "--input", str(workspace / "missing.yaml")]) == 1
    )


def test_update_cli_requires_approved_files(workspace: Path) -> None:
    assert cv.main(["begin-update"]) == 1


def test_doctor_checks_pip_consistency(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    command = workspace / "rendercv"
    command.touch()
    monkeypatch.setattr(cv, "get_rendercv_command", lambda: command)
    monkeypatch.setattr(cv.sys, "prefix", str(cv.VENV))
    versions = {"rendercv": "2.8", "pyyaml": "6.0.3", "jsonschema": "4.25.1", "pypdf": "6.2.0"}
    monkeypatch.setattr(metadata, "version", lambda name: versions[name])
    monkeypatch.setattr(
        cv.subprocess, "run", lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "", "")
    )
    assert cv.main(["doctor"]) == 0
    monkeypatch.setattr(
        cv.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, "broken", ""),
    )
    with pytest.raises(cv.CVError, match="pip check failed"):
        cv.doctor()


def test_doctor_reports_uninstalled_packages(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(_name: str) -> str:
        raise metadata.PackageNotFoundError()

    monkeypatch.setattr(metadata, "version", missing)
    with pytest.raises(cv.CVError, match="Doctor found problems"):
        cv.doctor()
