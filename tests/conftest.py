"""No real candidate data is used in automated tests."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import cv


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    original_root = cv.ROOT
    for folder in ("schemas", "templates", "data", "resumes", "output"):
        (tmp_path / folder).mkdir()
    shutil.copy2(original_root / "schemas" / "profile.schema.json", tmp_path / "schemas")
    shutil.copy2(original_root / "schemas" / "preferences.schema.json", tmp_path / "schemas")
    shutil.copy2(original_root / "templates" / "profile.example.yaml", tmp_path / "templates")
    shutil.copy2(original_root / "templates" / "preferences.example.yaml", tmp_path / "templates")
    shutil.copy2(original_root / "templates" / "rendercv.example.yaml", tmp_path / "templates")
    monkeypatch.setattr(cv, "ROOT", tmp_path)
    monkeypatch.setattr(cv, "DATA", tmp_path / "data")
    monkeypatch.setattr(cv, "PROFILE", tmp_path / "data" / "profile.yaml")
    monkeypatch.setattr(cv, "DRAFT", tmp_path / "data" / "profile.draft.yaml")
    monkeypatch.setattr(cv, "REVIEW", tmp_path / "data" / "intake-review.yaml")
    monkeypatch.setattr(cv, "SCHEMA", tmp_path / "schemas" / "profile.schema.json")
    monkeypatch.setattr(cv, "PREFERENCE_SCHEMA", tmp_path / "schemas" / "preferences.schema.json")
    monkeypatch.setattr(cv, "PREFERENCES", tmp_path / "data" / "preferences.yaml")
    monkeypatch.setattr(cv, "PREFERENCES_DRAFT", tmp_path / "data" / "preferences.draft.yaml")
    monkeypatch.setattr(cv, "VENV", tmp_path / ".venv")
    shutil.copy2(tmp_path / "templates" / "preferences.example.yaml", cv.PREFERENCES_DRAFT)
    return tmp_path


@pytest.fixture
def example_profile(workspace: Path) -> dict[str, Any]:
    data = yaml.safe_load((workspace / "templates" / "profile.example.yaml").read_text())
    data["candidate"]["full_name"] = "Test Candidate"
    return copy.deepcopy(data)


def save_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
