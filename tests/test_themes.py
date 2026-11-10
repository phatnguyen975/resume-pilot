"""Theme gallery, human-reviewed preferences, and RenderCV CLI integration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import cv
from tests.conftest import save_yaml
from tests.test_render import make_pdf, make_png
from tests.test_review import mark_approved

PDF_SAMPLE = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def test_theme_schema_matches_cli(workspace: Path) -> None:
    schema = json.loads(cv.PREFERENCE_SCHEMA.read_text(encoding="utf-8"))
    assert set(schema["properties"]["resume"]["properties"]["theme"]["enum"]) == set(cv.THEMES)
    assert set(cv.THEME_FILENAME) == set(cv.THEMES)
    assert len(cv.THEMES) == 9


@pytest.mark.parametrize("theme", ["harvard", "moderncv", "ember", "not-a-theme", None])
def test_preference_schema_rejects_unknown_theme(workspace: Path, theme: Any) -> None:
    preferences = cv.default_preferences()
    preferences["resume"]["theme"] = theme
    if theme in cv.THEMES:
        assert cv.validate_preferences(preferences) == preferences
    else:
        with pytest.raises(cv.CVError, match="Preferences schema"):
            cv.validate_preferences(preferences)


def test_preference_schema_rejects_bad_locale_and_pages(workspace: Path) -> None:
    preferences = cv.default_preferences()
    preferences["resume"]["target_pages"] = 0
    with pytest.raises(cv.CVError, match="Preferences schema"):
        cv.validate_preferences(preferences)
    preferences["resume"]["target_pages"] = 1
    preferences["resume"]["language"] = "klingon"
    with pytest.raises(cv.CVError, match="Preferences schema"):
        cv.validate_preferences(preferences)


def test_gallery_only_lists_original_upstream_filenames(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cv.list_themes() == 0
    output = capsys.readouterr().out
    for theme in cv.THEMES:
        assert f"examples/{cv.THEME_FILENAME[theme]}" in output
    assert output.count("missing") >= len(cv.THEMES)
    assert not (workspace / "examples").exists()
    assert not (workspace / "examples" / "themes").exists()


def test_previews_added_by_human_are_recognized_without_renaming(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = workspace / "examples"
    folder.mkdir()
    name = cv.THEME_FILENAME["harvard"]
    path = folder / name
    path.write_bytes(PDF_SAMPLE)
    assert cv.preview_status(path) == "ready"
    assert cv.list_themes() == 0
    output = capsys.readouterr().out
    assert f"ready      examples/{name}" in output
    assert path.read_bytes() == PDF_SAMPLE  # read-only command
    assert not (folder / "harvard.pdf").exists()


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"<html>not a PDF</html>", "invalid"),
        (b"%PDF-1.7\nNo end of file marker", "invalid"),
        (b"\n\n%%EOF\n", "invalid"),
        (b"%PDF-1.7\n%%EOF\n", "ready"),
        (b"", "invalid"),
    ],
)
def test_preview_validation_is_read_only(workspace: Path, payload: bytes, expected: str) -> None:
    folder = workspace / "examples"
    folder.mkdir()
    path = folder / cv.THEME_FILENAME["ink"]
    path.write_bytes(payload)
    assert cv.preview_status(path) == expected
    assert cv.list_themes() == 0
    assert path.read_bytes() == payload


def test_oversized_pdf_is_not_read(workspace: Path) -> None:
    folder = workspace / "examples"
    folder.mkdir()
    path = folder / cv.THEME_FILENAME["moderncv"]
    with path.open("wb") as file:
        file.truncate(12_000_001)
    assert cv.preview_status(path) == "invalid"
    assert path.stat().st_size == 12_000_001


def test_gallery_cli_lists_paths_without_modification(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cv.main(["themes"]) == 0
    output = capsys.readouterr().out
    assert "examples/John_Doe_ClassicTheme_CV.pdf" in output
    assert not (workspace / "examples").exists()


def test_examples_readme_matches_filenames() -> None:
    text = (Path(__file__).resolve().parents[1] / "examples" / "README.md").read_text()
    for name in cv.THEME_FILENAME.values():
        assert name in text
    assert "--download" not in text


def test_preferences_are_human_reviewed_and_stale_changes_blocked(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    save_yaml(cv.DRAFT, example_profile)
    prefs = cv.default_preferences()
    prefs["resume"]["theme"] = "harvard"
    save_yaml(cv.PREFERENCES_DRAFT, prefs)
    cv.prepare_review()
    assert cv.load_yaml(cv.REVIEW)["preferences_snapshot"]["resume"]["theme"] == "harvard"
    mark_approved(cv.REVIEW)
    prefs["resume"]["theme"] = "ember"
    save_yaml(cv.PREFERENCES_DRAFT, prefs)
    with pytest.raises(cv.CVError, match="preferences changed"):
        cv.approve()
    cv.prepare_review(replace=True)
    mark_approved(cv.REVIEW)
    cv.approve()
    assert cv.current_preferences()["resume"]["theme"] == "ember"
    assert not cv.PREFERENCES_DRAFT.exists()


def test_changed_preferences_snapshot_without_draft_rejected(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    review = cv.load_yaml(cv.REVIEW)
    review["preferences_snapshot"]["resume"]["theme"] = "ink"
    save_yaml(cv.REVIEW, review)
    with pytest.raises(cv.CVError, match="preferences snapshot"):
        cv.approve()


def test_begin_update_copies_approved_preferences_with_baseline(
    workspace: Path, example_profile: dict[str, Any]
) -> None:
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    cv.approve()
    current_hash = cv.path_digest(cv.PREFERENCES)
    cv.begin_update()
    draft = cv.load_yaml(cv.PREFERENCES_DRAFT)
    assert draft["base_preferences_sha256"] == current_hash
    draft["resume"]["theme"] = "opal"
    save_yaml(cv.PREFERENCES_DRAFT, draft)
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    cv.approve(replace=True)
    assert cv.current_preferences()["resume"]["theme"] == "opal"


def test_build_applies_approved_theme_and_temporary_override(
    workspace: Path, example_profile: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    save_yaml(cv.DRAFT, example_profile)
    pref = cv.default_preferences()
    pref["resume"]["theme"] = "harvard"
    pref["resume"]["target_pages"] = 1
    save_yaml(cv.PREFERENCES_DRAFT, pref)
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    cv.approve()

    cv_source = workspace / "resumes" / "master_cv.yaml"
    cv_source.write_text((workspace / "templates" / "rendercv.example.yaml").read_text())
    fake_engine = workspace / "fake-rendercv"
    fake_engine.write_text("fake")
    monkeypatch.setattr(cv, "get_rendercv_command", lambda: fake_engine)
    args_log: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        args_log.append(argv)
        make_pdf(Path(argv[argv.index("--pdf-path") + 1]))
        make_png(Path(argv[argv.index("--png-path") + 1]))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(cv.subprocess, "run", fake_run)
    cv.build(cv_source)
    assert args_log[-1][args_log[-1].index("--design.theme") + 1] == "harvard"
    report = json.loads((workspace / "output" / "master_cv" / "audit.json").read_text())
    assert report["theme"] == "harvard"
    assert report["theme_override"] is False
    cv.build(cv_source, theme="ink")
    assert args_log[-1][args_log[-1].index("--design.theme") + 1] == "ink"
    assert cv.current_preferences()["resume"]["theme"] == "harvard"


def test_invalid_theme_override_rejected(workspace: Path, example_profile: dict[str, Any]) -> None:
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    mark_approved(cv.REVIEW)
    cv.approve()
    source = workspace / "resumes" / "master_cv.yaml"
    source.write_text((workspace / "templates" / "rendercv.example.yaml").read_text())
    with pytest.raises(cv.CVError, match="Unknown theme"):
        cv.build(source, theme="unknown")
