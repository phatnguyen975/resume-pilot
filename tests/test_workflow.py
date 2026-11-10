"""Role-play a coding agent performing the actual workflow with synthetic facts.

The external RenderCV executable is simulated; deterministic CLI, review gate,
profile promotion, update conflict protection and document audit are real.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import cv
from tests.conftest import save_yaml
from tests.test_render import make_pdf, make_png


def test_agent_first_cv_update_and_tailor_end_to_end(
    workspace: Path, example_profile: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # First-time agent asks for facts; no approved profile means no real build.
    master = workspace / "resumes" / "master_cv.yaml"
    master.write_text((workspace / "templates" / "rendercv.example.yaml").read_text())
    with pytest.raises(cv.CVError, match="No approved"):
        cv.require_approved_for_build(master, example=False)

    # Agent writes a truthful-ish synthetic draft; a review file is generated.
    example_profile["candidate"]["email"] = "synthetic@example.org"
    save_yaml(cv.DRAFT, example_profile)
    cv.prepare_review()
    with pytest.raises(cv.CVError, match="not approved"):
        cv.approve()

    # Explicit simulated human approval.
    review = cv.load_yaml(cv.REVIEW)
    review["decision"] = "approved"
    review["reviewer"] = "synthetic test human"
    review["reviewed_at"] = "2026-11-10T14:00:00+07:00"
    save_yaml(cv.REVIEW, review)
    cv.approve()
    assert cv.PROFILE.is_file()
    assert not cv.DRAFT.exists()
    assert len(list((cv.DATA / "history").glob("review-*.yaml"))) == 1

    # Agent constructs the RenderCV YAML, and a fake render checks CLI integration.
    fake_engine = workspace / "rendercv-fake"
    fake_engine.write_text("fake")
    monkeypatch.setattr(cv, "get_rendercv_command", lambda: fake_engine)

    def mock_engine(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        make_pdf(Path(argv[argv.index("--pdf-path") + 1]), text="Synthetic Test Candidate")
        make_png(Path(argv[argv.index("--png-path") + 1]))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(cv.subprocess, "run", mock_engine)
    initial = cv.build(master)
    assert cv.pdf_report(initial / "resume.pdf")["passed"]

    # Add a new confirmed project through another explicit approval cycle.
    cv.begin_update()
    updated = cv.load_yaml(cv.DRAFT)
    updated["projects"].append(
        {
            "id": "project-new",
            "name": "New Mobile App",
            "technologies": ["React Native"],
            "verification": "confirmed",
            "evidence": ["human:test"],
            "highlights": [
                {
                    "text": "Developed an example mobile app.",
                    "verification": "confirmed",
                    "evidence": ["human:test"],
                }
            ],
        }
    )
    save_yaml(cv.DRAFT, updated)
    cv.prepare_review()
    review = cv.load_yaml(cv.REVIEW)
    review["decision"] = "approved"
    review["reviewer"] = "synthetic test human"
    review["reviewed_at"] = "2026-11-10T15:00:00+07:00"
    save_yaml(cv.REVIEW, review)
    cv.approve(replace=True)
    assert any(x["id"] == "project-new" for x in cv.load_yaml(cv.PROFILE)["projects"])

    # Agent creates a job-specific CV; approved data remains untouched by render.
    before = cv.path_digest(cv.PROFILE)
    targeted = workspace / "resumes" / "targeted" / "mobile_developer_cv.yaml"
    targeted.parent.mkdir()
    targeted.write_text(master.read_text())
    result = cv.build(targeted)
    assert result.name == "mobile_developer_cv"
    assert cv.path_digest(cv.PROFILE) == before
