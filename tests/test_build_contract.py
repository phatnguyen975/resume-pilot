"""Rendering contracts independent of the external engine."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfWriter

from scripts import cv
from tests.conftest import save_yaml
from tests.test_recovery import reviewed_draft
from tests.test_render import make_pdf, make_png


@pytest.fixture
def engine(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    executable = workspace / "fake_rendercv"
    executable.touch()
    monkeypatch.setattr(cv, "get_rendercv_command", lambda: executable)
    calls: list[list[str]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
        assert "--quiet" in argv
        make_pdf(Path(argv[argv.index("--pdf-path") + 1]))
        make_png(Path(argv[argv.index("--png-path") + 1]))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(cv.subprocess, "run", run)
    return calls


@pytest.mark.parametrize("target", [1, 2])
def test_pdf_target_is_exact_not_only_a_maximum(workspace: Path, target: int) -> None:
    pdf = workspace / "one.pdf"
    make_pdf(pdf)
    report = cv.pdf_report(pdf, max_pages=target, target_pages=target)
    assert report["passed"] is (target == 1)
    assert report["target_pages"] == target
    if target == 2:
        assert "requested exactly 2" in report["warnings"][0]


def test_pdf_rejects_invalid_target_and_zero_pages(workspace: Path) -> None:
    path = workspace / "empty.pdf"
    with path.open("wb") as stream:
        PdfWriter().write(stream)
    with pytest.raises(cv.CVError, match="target_pages"):
        cv.pdf_report(path, target_pages=0)
    report = cv.pdf_report(path)
    assert not report["passed"] and "zero pages" in report["warnings"][0]


def test_failed_audit_preserves_previous_pdf_and_records_attempt(
    workspace: Path, engine: list[list[str]]
) -> None:
    source = workspace / "templates/rendercv.example.yaml"
    output = cv.build(source, example=True)
    previous = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(cv.CVError, match="requested exactly 2"):
        cv.build(source, example=True, max_pages=2)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == previous
    attempt = next((workspace / "output/failed/rendercv.example").iterdir())
    report = json.loads((attempt / "audit.json").read_text(encoding="utf-8"))
    assert report["target_pages"] == 2 and report["pages"] == 1
    assert report["page_target_override"] and not report["passed"]


def test_one_time_page_target_does_not_change_preferences(
    workspace: Path, example_profile: dict[str, Any], engine: list[list[str]]
) -> None:
    prefs = cv.load_yaml(cv.PREFERENCES_DRAFT)
    prefs["resume"]["target_pages"] = 2
    save_yaml(cv.PREFERENCES_DRAFT, prefs)
    reviewed_draft(example_profile)
    cv.approve()
    source = workspace / "resumes/master_cv.yaml"
    source.write_bytes((workspace / "templates/rendercv.example.yaml").read_bytes())
    before = cv.path_digest(cv.PREFERENCES)
    output = cv.build(source, max_pages=1)
    report = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    assert report["pages"] == report["target_pages"] == 1
    assert cv.path_digest(cv.PREFERENCES) == before


def test_same_stem_in_another_folder_does_not_overwrite_output(
    workspace: Path, example_profile: dict[str, Any], engine: list[list[str]]
) -> None:
    reviewed_draft(example_profile)
    cv.approve()
    source = workspace / "resumes/master_cv.yaml"
    source.write_bytes((workspace / "templates/rendercv.example.yaml").read_bytes())
    output = cv.build(source)
    digest = cv.path_digest(output / "resume.pdf")
    other = source.parent / "targeted" / source.name
    other.parent.mkdir()
    other.write_bytes(source.read_bytes())
    with pytest.raises(cv.CVError, match="collision"):
        cv.build(other)
    assert cv.path_digest(output / "resume.pdf") == digest
    assert len(engine) == 1


@pytest.mark.parametrize("metadata", [None, "not json", "[]"])
def test_output_without_reliable_source_metadata_is_preserved(
    workspace: Path, engine: list[list[str]], metadata: str | None
) -> None:
    output = workspace / "output/rendercv.example"
    output.mkdir()
    (output / "resume.pdf").write_bytes(b"preserve")
    if metadata is not None:
        (output / "audit.json").write_text(metadata, encoding="utf-8")
    with pytest.raises(cv.CVError, match="metadata"):
        cv.build(workspace / "templates/rendercv.example.yaml", example=True)
    assert (output / "resume.pdf").read_bytes() == b"preserve" and not engine


@pytest.mark.parametrize("name", ["bad-name_cv.yaml", "Master_cv.yaml", "master_cv.txt"])
def test_real_cv_names_follow_documented_convention(
    workspace: Path, example_profile: dict[str, Any], engine: list[list[str]], name: str
) -> None:
    reviewed_draft(example_profile)
    cv.approve()
    source = workspace / "resumes" / name
    source.write_bytes((workspace / "templates/rendercv.example.yaml").read_bytes())
    with pytest.raises(cv.CVError, match="snake_case"):
        cv.build(source)
    assert not engine


@pytest.mark.parametrize("kind", ["extra", "corrupt"])
def test_preview_count_and_header_are_checked(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, engine: list[list[str]], kind: str
) -> None:
    original = cv.subprocess.run

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        result = original(argv, **kwargs)
        png = Path(argv[argv.index("--png-path") + 1])
        if kind == "extra":
            make_png(png.with_name("extra.png"))
        else:
            png.write_bytes(b"not a PNG")
        return result

    monkeypatch.setattr(cv.subprocess, "run", run)
    with pytest.raises(cv.CVError, match=r"Preview PNG count|Invalid preview PNG"):
        cv.build(workspace / "templates/rendercv.example.yaml", example=True)


def test_publish_failure_restores_old_output_directory(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, engine: list[list[str]]
) -> None:
    source = workspace / "templates/rendercv.example.yaml"
    output = cv.build(source, example=True)
    previous = {p.name: p.read_bytes() for p in output.iterdir()}
    rename = Path.rename

    def fail_publish(path: Path, target: Path) -> Path:
        if path.name.startswith(".publish_"):
            assert path.parent == output.parent
            raise OSError("publish unavailable")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_publish)
    with pytest.raises(OSError, match="publish"):
        cv.build(source, example=True)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == previous


def test_failed_output_recovery_keeps_backup_outside_temporary_stage(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, engine: list[list[str]]
) -> None:
    source = workspace / "templates/rendercv.example.yaml"
    output = cv.build(source, example=True)
    previous = (output / "resume.pdf").read_bytes()
    rename = Path.rename

    def fail_publish_and_restore(path: Path, target: Path) -> Path:
        if path.name.startswith(".publish_") or path.name == "artifacts":
            raise OSError("destination locked")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_publish_and_restore)
    with pytest.raises(cv.CVError, match="previous build is safe"):
        cv.build(source, example=True)
    backup = next((workspace / "output").glob(".previous_*/artifacts/resume.pdf"))
    assert backup.read_bytes() == previous
