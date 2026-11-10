from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("filename", ["profile.schema.json", "preferences.schema.json"])
def test_schemas_are_valid_json_schema(filename: str) -> None:
    schema = json.loads((ROOT / "schemas" / filename).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)


def test_all_agent_skills_have_valid_frontmatter() -> None:
    directories = sorted((ROOT / ".agents" / "skills").iterdir())
    assert len(directories) == 4
    for directory in directories:
        path = directory / "SKILL.md"
        assert path.is_file()
        contents = path.read_text()
        assert contents.startswith("---\n")
        frontmatter = yaml.safe_load(contents.split("---", 2)[1])
        assert frontmatter["name"] == directory.name
        assert len(frontmatter["description"]) > 30


def test_personal_and_generated_directories_are_gitignored() -> None:
    ignore = (ROOT / ".gitignore").read_text()
    for name in ("data", "jobs", "resumes", "output", ".venv"):
        assert f"/{name}/" in ignore


def test_readme_and_agent_contract_reference_required_human_gate() -> None:
    agent = (ROOT / "AGENTS.md").read_text()
    readme = (ROOT / "README.md").read_text()
    for text in ("intake-review.yaml", "approve", "profile.draft.yaml", "resume-audit"):
        assert text in agent
        assert text in readme
