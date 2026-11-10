from __future__ import annotations

import base64
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from scripts import cv
from tests.conftest import save_yaml


def make_png(path: Path) -> None:
    path.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aLTsAAAAASUVORK5CYII="
        )
    )


def make_pdf(path: Path, *, text: str = "A test candidate has worked on reliable code.") -> None:
    """Write a small PDF with an extractable standard-font content stream."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as output:
        writer.write(output)


def test_basic_resume_yaml_valid(workspace: Path) -> None:
    cv.validate_resume_basic(cv.load_yaml(workspace / "templates" / "rendercv.example.yaml"))


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"cv": []},
        {"cv": {"name": "No sections"}},
        {"cv": {"name": "", "sections": {"skills": ["ok"]}}},
        {"cv": {"name": "Name", "sections": {"skills": []}}},
        {"cv": {"name": "Name", "sections": {"skills": [3]}}},
        {"cv": {"name": "Name", "sections": {"skills": ["ok"]}}, "wrong": {}},
        {"cv": {"name": "Name", "sections": {"skills": ["ok"]}}, "design": []},
    ],
)
def test_invalid_resume_preflight_rejected(payload: Any) -> None:
    with pytest.raises(cv.CVError):
        cv.validate_resume_basic(payload)


def test_build_rejects_unapproved_profile(workspace: Path) -> None:
    source = workspace / "resumes" / "master_cv.yaml"
    source.write_text((workspace / "templates" / "rendercv.example.yaml").read_text())
    with pytest.raises(cv.CVError, match="No approved"):
        cv.require_approved_for_build(source, example=False)


def test_example_flag_is_not_a_bypass_for_other_files(workspace: Path) -> None:
    with pytest.raises(cv.CVError, match="only permits"):
        cv.require_approved_for_build(workspace / "resumes" / "real_cv.yaml", example=True)


def test_nonexample_must_be_in_resumes(workspace: Path, example_profile: dict[str, Any]) -> None:
    save_yaml(cv.PROFILE, example_profile)
    with pytest.raises(cv.CVError, match="under resumes"):
        cv.require_approved_for_build(
            workspace / "templates" / "rendercv.example.yaml", example=False
        )


def test_pdf_report_success(workspace: Path) -> None:
    pdf = workspace / "sample.pdf"
    make_pdf(pdf)
    result = cv.pdf_report(pdf)
    assert result["passed"]
    assert result["pages"] == 1
    assert result["characters"] >= 20
    assert result["link_annotations"] == 0


def test_pdf_report_rejects_empty_text(workspace: Path) -> None:
    pdf = workspace / "empty.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with pdf.open("wb") as destination:
        writer.write(destination)
    result = cv.pdf_report(pdf)
    assert not result["passed"]
    assert "insufficient" in result["warnings"][0]


def test_pdf_report_rejects_invalid_and_missing_pdfs(workspace: Path) -> None:
    with pytest.raises(cv.CVError, match="not found"):
        cv.pdf_report(workspace / "not-here.pdf")
    corrupt = workspace / "bad.pdf"
    corrupt.write_bytes(b"not actually a PDF")
    with pytest.raises(cv.CVError, match="cannot be inspected"):
        cv.pdf_report(corrupt)


def test_pdf_max_pages_enforced(workspace: Path) -> None:
    pdf = workspace / "many.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    with pdf.open("wb") as target:
        writer.write(target)
    assert any("requested max" in issue for issue in cv.pdf_report(pdf, max_pages=1)["warnings"])
    with pytest.raises(cv.CVError, match="max-pages"):
        cv.pdf_report(pdf, max_pages=0)


def test_build_with_mock_render_engine_happy_path(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_executable = workspace / "fake-rendercv"
    fake_executable.write_text("fake")
    monkeypatch.setattr(cv, "get_rendercv_command", lambda: fake_executable)

    def fake_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        pdf = Path(argv[argv.index("--pdf-path") + 1])
        png = Path(argv[argv.index("--png-path") + 1])
        make_pdf(pdf)
        make_png(png)
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(cv.subprocess, "run", fake_run)
    result = cv.build(workspace / "templates" / "rendercv.example.yaml", example=True)
    assert (result / "resume.pdf").is_file()
    assert (result / "preview.png").exists()
    assert cv.load_yaml(workspace / "templates" / "rendercv.example.yaml")
    import json

    assert json.loads((result / "audit.json").read_text())["passed"]


def test_build_failing_render_preserves_previous_output(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = workspace / "fake-rendercv"
    executable.write_text("fake")
    monkeypatch.setattr(cv, "get_rendercv_command", lambda: executable)
    prior = workspace / "output" / "rendercv.example" / "resume.pdf"
    prior.parent.mkdir(parents=True)
    prior.write_bytes(b"prior valid artifact")
    import json

    (prior.parent / "audit.json").write_text(
        json.dumps({"source": "templates/rendercv.example.yaml"})
    )
    monkeypatch.setattr(
        cv.subprocess, "run", lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, "", "bad")
    )
    with pytest.raises(cv.CVError, match="RenderCV failed"):
        cv.build(workspace / "templates" / "rendercv.example.yaml", example=True)
    assert prior.read_bytes() == b"prior valid artifact"


def test_build_rejects_missing_pdf_after_success(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_executable = workspace / "fake-rendercv"
    fake_executable.write_text("fake")
    monkeypatch.setattr(cv, "get_rendercv_command", lambda: fake_executable)
    monkeypatch.setattr(
        cv.subprocess, "run", lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "", "")
    )
    with pytest.raises(cv.CVError, match="no PDF"):
        cv.build(workspace / "templates" / "rendercv.example.yaml", example=True)


def test_build_requires_previews(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_executable = workspace / "fake-rendercv"
    fake_executable.write_text("fake")
    monkeypatch.setattr(cv, "get_rendercv_command", lambda: fake_executable)

    def no_png(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        make_pdf(Path(argv[argv.index("--pdf-path") + 1]))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(cv.subprocess, "run", no_png)
    with pytest.raises(cv.CVError, match="No preview PNG"):
        cv.build(workspace / "templates" / "rendercv.example.yaml", example=True)
