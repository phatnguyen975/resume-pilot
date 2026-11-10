from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from scripts import cv


def test_example_profile_is_schema_valid(example_profile: dict[str, Any]) -> None:
    result = cv.validate_profile(example_profile)
    assert result["candidate"]["full_name"] == "Test Candidate"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("candidate", "email"), "not-an-email"),
        (("candidate", "verification"), "guessed"),
        (("skills", 0, "category"), 7),
        (("projects", 0, "start_date"), "2025-18"),
        (("experience", 0, "bogus"), "ignored?"),
    ],
)
def test_bad_profile_fields_rejected(
    example_profile: dict[str, Any], path: tuple[str | int, ...], value: Any
) -> None:
    data = copy.deepcopy(example_profile)
    node: Any = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(cv.CVError, match="schema validation"):
        cv.validate_profile(data)


def test_duplicate_ids_cross_categories_are_rejected(example_profile: dict[str, Any]) -> None:
    example_profile["skills"][0]["id"] = "project-example"
    with pytest.raises(cv.CVError, match="Duplicate ID"):
        cv.validate_profile(example_profile)


def test_reversed_dates_rejected(example_profile: dict[str, Any]) -> None:
    example_profile["education"][0]["start_date"] = "2025-01"
    with pytest.raises(cv.CVError, match="Invalid date range"):
        cv.validate_profile(example_profile)


def test_confirmed_candidate_required_for_promotion(example_profile: dict[str, Any]) -> None:
    example_profile["candidate"]["verification"] = "needs_review"
    cv.validate_profile(example_profile)
    with pytest.raises(cv.CVError, match="identity/contact"):
        cv.validate_profile(example_profile, for_approval=True)


def test_example_identity_cannot_be_approved(example_profile: dict[str, Any]) -> None:
    example_profile["candidate"]["full_name"] = "Example Candidate"
    with pytest.raises(cv.CVError, match="fictional"):
        cv.validate_profile(example_profile, for_approval=True)


def test_unverified_record_and_bullet_are_reported(example_profile: dict[str, Any]) -> None:
    example_profile["skills"][0]["verification"] = "inferred"
    example_profile["projects"][0]["highlights"][0]["verification"] = "needs_review"
    result = cv.unresolved_paths(example_profile)
    assert "skills.skill-python" in result
    assert "projects.project-example.highlights[0]" in result


def test_yaml_duplicate_keys_rejected(workspace: Path) -> None:
    path = workspace / "data" / "bad.yaml"
    path.write_text("candidate: test\ncandidate: other\n")
    with pytest.raises(cv.CVError, match="Duplicate YAML key"):
        cv.load_yaml(path)


def test_yaml_syntax_error_rejected(workspace: Path) -> None:
    path = workspace / "data" / "bad.yaml"
    path.write_text("candidate: [\n")
    with pytest.raises(cv.CVError, match="Invalid YAML"):
        cv.load_yaml(path)


def test_yaml_missing_file_rejected(workspace: Path) -> None:
    with pytest.raises(cv.CVError, match="Invalid YAML"):
        cv.load_yaml(workspace / "data" / "missing.yaml")


def test_profile_rejects_nonmapping_root() -> None:
    with pytest.raises(cv.CVError, match="root must be"):
        cv.validate_profile(["not", "mapping"])
