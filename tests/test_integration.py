"""Real engine checks using only fictional data in isolated workspaces."""

from __future__ import annotations

import json
import os
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfReader

from scripts import cv
from tests.conftest import save_yaml
from tests.test_recovery import reviewed_draft

ENGINE = cv.get_rendercv_command()
ARTIFACTS = Path(
    os.environ.get(
        "RESUME_PILOT_TEST_ARTIFACTS", str(cv.ROOT / "output" / "quality" / "integration")
    )
)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("theme", "language"),
    [(theme, "english") for theme in cv.THEMES] + [("engineeringresumes", "vietnamese")],
)
def test_real_render_matches_reviewed_preferences(
    workspace: Path,
    example_profile: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    theme: str,
    language: str,
) -> None:
    prefs = cv.load_yaml(cv.PREFERENCES_DRAFT)
    prefs["resume"].update(theme=theme, language=language, target_pages=1)
    save_yaml(cv.PREFERENCES_DRAFT, prefs)
    reviewed_draft(example_profile)
    cv.approve()
    source = workspace / "resumes" / f"{theme}_cv.yaml"
    resume = cv.load_yaml(workspace / "templates/rendercv.example.yaml")
    resume["cv"]["name"] = example_profile["candidate"]["full_name"]
    if language == "vietnamese":
        resume["cv"]["sections"]["experience"][0]["highlights"] = [
            "Lập báo cáo mẫu ghi nhận các quan sát về quy trình."
        ]
    save_yaml(source, resume)
    monkeypatch.setattr(cv, "get_rendercv_command", lambda: ENGINE)
    before = cv.path_digest(cv.PREFERENCES)
    output = cv.build(source)
    report = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    assert report["passed"] and report["pages"] == report["target_pages"] == 1
    assert report["theme"] == theme and report["language"] == language
    assert len(report["previews"]) == 1
    reader = PdfReader(output / "resume.pdf")
    text = unicodedata.normalize(
        "NFC", "\n".join(page.extract_text() or "" for page in reader.pages)
    )
    # Font kerning can introduce whitespace inside words during PDF extraction.
    assert "TestCandidate" in "".join(text.split())
    assert report["link_annotations"] >= 2
    if language == "vietnamese":
        assert "Lập báo cáo" in text
    assert cv.path_digest(cv.PREFERENCES) == before
    assert not (workspace / "templates/rendercv_output").exists()
    assert not (workspace / "resumes/rendercv_output").exists()
    # Keep only synthetic render artifacts for a separate visual review.
    destination = ARTIFACTS / f"{theme}_{language}"
    destination.mkdir(parents=True, exist_ok=True)
    for item in output.iterdir():
        (destination / item.name).write_bytes(item.read_bytes())


@pytest.mark.integration
def test_real_two_page_cv_has_two_previews(
    workspace: Path, example_profile: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    prefs = cv.load_yaml(cv.PREFERENCES_DRAFT)
    prefs["resume"]["target_pages"] = 2
    save_yaml(cv.PREFERENCES_DRAFT, prefs)
    projects = [
        {
            "id": f"project-{index}",
            "name": f"Synthetic research study {index}",
            "summary": (
                "A fictional study documenting a distinct operations process for test purposes."
            ),
            "highlights": [
                {
                    "text": (
                        "Prepared a fictional analysis of the process "
                        "and documented the observations."
                    ),
                    "verification": "confirmed",
                },
                {
                    "text": (
                        "Presented the synthetic study findings in a structured internal report."
                    ),
                    "verification": "confirmed",
                },
            ],
            "verification": "confirmed",
        }
        for index in range(12)
    ]
    example_profile["projects"] = [*example_profile.get("projects", []), *projects]
    reviewed_draft(example_profile)
    cv.approve()
    resume = cv.load_yaml(workspace / "templates/rendercv.example.yaml")
    resume["cv"]["name"] = example_profile["candidate"]["full_name"]
    resume["cv"]["sections"]["projects"] = [
        {
            "name": p["name"],
            "summary": p["summary"],
            "highlights": [h["text"] for h in p["highlights"]],
        }
        for p in projects
    ]
    source = workspace / "resumes/research_cv.yaml"
    save_yaml(source, resume)
    monkeypatch.setattr(cv, "get_rendercv_command", lambda: ENGINE)
    output = cv.build(source)
    report = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    assert report["pages"] == report["target_pages"] == len(report["previews"]) == 2
    destination = ARTIFACTS / "two_pages"
    destination.mkdir(parents=True, exist_ok=True)
    for item in output.iterdir():
        (destination / item.name).write_bytes(item.read_bytes())
