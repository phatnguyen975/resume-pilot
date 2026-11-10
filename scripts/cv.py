"""Resume Pilot CLI: review gate, profile validation, RenderCV build, and PDF audit.

Use `python scripts/bootstrap.py` first. The CLI re-launches itself using .venv Python.
"""

from __future__ import annotations

import argparse
import calendar
import copy
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
DATA = ROOT / "data"
PROFILE = DATA / "profile.yaml"
DRAFT = DATA / "profile.draft.yaml"
REVIEW = DATA / "intake-review.yaml"
SCHEMA = ROOT / "schemas" / "profile.schema.json"
PREFERENCE_SCHEMA = ROOT / "schemas" / "preferences.schema.json"
PREFERENCES = DATA / "preferences.yaml"
PREFERENCES_DRAFT = DATA / "preferences.draft.yaml"
THEMES = (
    "classic",
    "engineeringresumes",
    "engineeringclassic",
    "harvard",
    "sb2nov",
    "moderncv",
    "ink",
    "opal",
    "ember",
)
THEME_FILENAME = {
    "classic": "John_Doe_ClassicTheme_CV.pdf",
    "engineeringresumes": "John_Doe_EngineeringresumesTheme_CV.pdf",
    "engineeringclassic": "John_Doe_EngineeringclassicTheme_CV.pdf",
    "harvard": "John_Doe_HarvardTheme_CV.pdf",
    "sb2nov": "John_Doe_Sb2novTheme_CV.pdf",
    "moderncv": "John_Doe_ModerncvTheme_CV.pdf",
    "ink": "John_Doe_InkTheme_CV.pdf",
    "opal": "John_Doe_OpalTheme_CV.pdf",
    "ember": "John_Doe_EmberTheme_CV.pdf",
}
FACT_GROUPS = (
    "skills",
    "experience",
    "projects",
    "education",
    "certifications",
    "awards",
    "publications",
    "volunteering",
    "languages",
    "additional",
)
VERIFY = ("confirmed", "needs_review", "inferred")


class CVError(Exception):
    """A user-actionable error (printed without a traceback)."""


def get_venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def get_rendercv_command() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "rendercv.exe"
    return VENV / "bin" / "rendercv"


def reexec_if_needed(argv: list[str]) -> int | None:
    """Do not require users to activate the venv manually."""
    if not argv or argv[0] in ("-h", "--help", "themes"):
        return None
    python = get_venv_python()
    if not python.is_file():
        raise CVError("Missing .venv. Run `python scripts/bootstrap.py` first.")
    if Path(sys.prefix).resolve() == VENV.resolve():
        return None
    completed = subprocess.run(
        [str(python), str(Path(__file__).resolve()), *argv],
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    return completed.returncode


def path_digest(path: Path) -> str:
    if not path.is_file():
        raise CVError(f"File not found: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_yaml(path: Path) -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise CVError("Missing PyYAML. Run `python scripts/bootstrap.py`.") from exc

    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def no_duplicate_keys(loader: UniqueKeyLoader, node: yaml.MappingNode) -> dict[Any, Any]:
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=True)
            if not isinstance(key, str):
                raise CVError(f"YAML mapping keys must be strings in {path}")
            if key in mapping:
                raise CVError(f"Duplicate YAML key {key!r} in {path}")
            mapping[key] = loader.construct_object(value_node, deep=True)
        return mapping

    UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, no_duplicate_keys
    )
    try:
        return yaml.load(path.read_text(encoding="utf-8-sig"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CVError(f"Invalid YAML {path}: {exc}") from exc


def write_yaml_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    import yaml

    content = yaml.safe_dump(
        dict(payload), sort_keys=False, allow_unicode=True, default_flow_style=False, width=100
    )
    write_atomic(path, content)


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_yaml_pair(
    first: Path, first_data: Mapping[str, Any], second: Path, second_data: Mapping[str, Any]
) -> None:
    """Restore both previous files if either atomic write fails (not a crash transaction)."""
    previous = {path: path.read_bytes() if path.exists() else None for path in (first, second)}
    try:
        write_yaml_atomic(first, first_data)
        write_yaml_atomic(second, second_data)
    except OSError as exc:
        try:
            for path, content in previous.items():
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    write_atomic(path, content.decode("utf-8"))
        except OSError as recovery_error:
            raise CVError(
                "Write and recovery failed; preserve drafts and restore backups"
            ) from recovery_error
        raise CVError("Paired write failed; previous files restored and drafts preserved") from exc


def date_bounds(value: str) -> tuple[dt.date, dt.date] | None:
    """Validate a YYYY / YYYY-MM / YYYY-MM-DD date and return possible bounds."""
    if value == "present":
        return None
    if re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", value) is None:
        raise CVError(f"Invalid calendar date: {value!r}")
    try:
        parts = value.split("-")
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        start = dt.date(year, month, day)
        if len(parts) == 3:
            return start, start
        last_month = month if len(parts) == 2 else 12
        last_day = calendar.monthrange(year, last_month)[1]
        return start, dt.date(year, last_month, last_day)
    except (ValueError, IndexError) as exc:
        raise CVError(f"Invalid calendar date: {value!r}") from exc


def validate_profile(data: Any, *, for_approval: bool = False) -> dict[str, Any]:
    try:
        import jsonschema
    except ImportError as exc:
        raise CVError("Missing jsonschema. Run `python scripts/bootstrap.py`.") from exc
    if not isinstance(data, dict):
        raise CVError("Profile root must be a mapping")
    schema: Any = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(data), key=lambda issue: issue.json_path)
    if errors:
        lines = [f"  {error.json_path}: {error.message}" for error in errors[:12]]
        raise CVError("Profile schema validation failed:\n" + "\n".join(lines))
    ids: dict[str, str] = {}
    for group in FACT_GROUPS:
        for index, record in enumerate(data.get(group, [])):
            item_id = record["id"]
            if item_id in ids:
                raise CVError(f"Duplicate ID {item_id!r}: {ids[item_id]} and {group}[{index}]")
            ids[item_id] = f"{group}[{index}]"
            start, end = record.get("start_date"), record.get("end_date")
            if start == "present":
                raise CVError(f"Start date cannot be present for {item_id}")
            start_bounds = date_bounds(start) if start else None
            end_bounds = date_bounds(end) if end else None
            if (
                start_bounds is not None
                and end_bounds is not None
                and start_bounds[0] > end_bounds[1]
            ):
                raise CVError(f"Invalid date range for {item_id}: {start} > {end}")
            if record.get("date"):
                date_bounds(record["date"])
    if for_approval:
        candidate = data["candidate"]
        if candidate["verification"] != "confirmed":
            raise CVError("Candidate identity/contact needs explicit confirmation before approval")
        if candidate["full_name"].casefold() == "example candidate":
            raise CVError("Replace the fictional Example Candidate with the real person's name")
    return cast(dict[str, Any], data)


def default_preferences() -> dict[str, Any]:
    """Load the explicit starter preference file, never personal information."""
    return validate_preferences(load_yaml(ROOT / "templates" / "preferences.example.yaml"))


def validate_preferences(data: Any) -> dict[str, Any]:
    try:
        import jsonschema
    except ImportError as exc:
        raise CVError("Missing jsonschema. Run `python scripts/bootstrap.py`.") from exc
    schema = json.loads(PREFERENCE_SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(data),
        key=lambda issue: issue.json_path,
    )
    if errors:
        descriptions = "\n".join(f"  {issue.json_path}: {issue.message}" for issue in errors[:12])
        raise CVError(f"Preferences schema validation failed:\n{descriptions}")
    return cast(dict[str, Any], data)


def current_preferences(*, example: bool = False) -> dict[str, Any]:
    if example:
        return default_preferences()
    if not PREFERENCES.is_file():
        raise CVError("Missing approved data/preferences.yaml. Complete intake human gate first")
    return validate_preferences(load_yaml(PREFERENCES))


def is_pdf_header_valid(payload: bytes) -> bool:
    return payload.startswith(b"%PDF-") and b"%%EOF" in payload[-2048:]


def preview_status(path: Path) -> str:
    """Inspect a manually supplied upstream PDF without modifying it or accessing the network."""
    if not path.is_file():
        return "missing"
    try:
        size = path.stat().st_size
        if size < 10 or size > 12_000_000:
            return "invalid"
        with path.open("rb") as stream:
            header = stream.read(8)
            stream.seek(max(0, size - 2048))
            trailer = stream.read()
        return "ready" if is_pdf_header_valid(header + trailer) else "invalid"
    except OSError:
        return "unreadable"


def list_themes() -> int:
    """List local official preview names; downloads and renaming are the user's choice."""
    folder = ROOT / "examples"
    missing = 0
    for theme in THEMES:
        path = folder / THEME_FILENAME[theme]
        status = preview_status(path)
        missing += status != "ready"
        print(f"{theme:22} {status:10} {path.relative_to(ROOT).as_posix()}")
    if missing:
        print(
            f"{missing} preview(s) not ready. Download official PDFs manually using "
            "examples/README.md and keep their original filenames."
        )
    return 0


def unresolved_paths(profile: Mapping[str, Any]) -> list[str]:
    unresolved: list[str] = []
    candidate: dict[str, Any] = profile["candidate"]
    if candidate["verification"] != "confirmed":
        unresolved.append("candidate")
    for group in FACT_GROUPS:
        for record in profile.get(group, []):
            if record["verification"] != "confirmed":
                unresolved.append(f"{group}.{record['id']}")
            for idx, claim in enumerate(record.get("highlights", [])):
                if claim["verification"] != "confirmed":
                    unresolved.append(f"{group}.{record['id']}.highlights[{idx}]")
    return unresolved


def reviewed_summary(profile: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "full_name": profile["candidate"]["full_name"],
        "target_roles": profile.get("target_roles", []),
        "record_counts": {group: len(profile.get(group, [])) for group in FACT_GROUPS},
        "unverified_paths": unresolved_paths(profile),
        "open_questions": profile.get("open_questions", []),
    }


def begin_update(draft: Path | None = None, *, replace: bool = False) -> None:
    if draft is None:
        draft = DRAFT
    if not PROFILE.is_file():
        raise CVError("No approved profile. Begin with intake instead of begin-update")
    if (draft.exists() or PREFERENCES_DRAFT.exists()) and not replace:
        raise CVError("Draft already exists. Do not overwrite unfinished intake")
    prefs = copy.deepcopy(current_preferences())
    prefs["base_preferences_sha256"] = path_digest(PREFERENCES)
    data = validate_profile(load_yaml(PROFILE))
    data = copy.deepcopy(data)
    data["base_profile_sha256"] = path_digest(PROFILE)
    write_yaml_pair(draft, data, PREFERENCES_DRAFT, prefs)
    print(f"Update draft: {draft}")


def prepare_review(
    draft: Path | None = None, output: Path | None = None, *, replace: bool = False
) -> None:
    if draft is None:
        draft = DRAFT
    if output is None:
        output = REVIEW
    profile = validate_profile(load_yaml(draft))
    if not PREFERENCES_DRAFT.is_file():
        raise CVError("Missing preferences draft. Ask the human for presentation choices first")
    preferences = validate_preferences(load_yaml(PREFERENCES_DRAFT))
    digest = path_digest(draft)
    preference_digest = path_digest(PREFERENCES_DRAFT)
    if output.exists() and not replace:
        old = load_yaml(output)
        if (
            isinstance(old, dict)
            and old.get("draft_sha256") == digest
            and old.get("preferences_sha256") == preference_digest
        ):
            validate_review(old, draft)
            print(f"Review already exists for this draft: {output}")
            return
        raise CVError("Review is stale. Re-run `review --replace` AFTER checking changes")
    payload = {
        "schema_version": 1,
        "draft_sha256": digest,
        "preferences_sha256": preference_digest,
        "preferences_snapshot": preferences,
        "decision": "pending",
        "reviewer": None,
        "reviewed_at": None,
        "acknowledge_exclusions": False,
        "notes": "Review ALL fields under profile_snapshot; request fixes before approval.",
        "summary": reviewed_summary(profile),
        "profile_snapshot": profile,
    }
    write_yaml_atomic(output, payload)
    print(f"Human review required: {output}")
    print("Ask the human to verify EVERY fact. Never change decision without explicit approval.")


def validate_review(review: Any, draft: Path) -> dict[str, Any]:
    if (
        not isinstance(review, dict)
        or type(review.get("schema_version")) is not int
        or review.get("schema_version") != 1
    ):
        raise CVError("Invalid intake review structure/version")
    for required in (
        "draft_sha256",
        "preferences_sha256",
        "preferences_snapshot",
        "decision",
        "summary",
        "profile_snapshot",
    ):
        if required not in review:
            raise CVError(f"Review missing required key {required!r}")
    if review["draft_sha256"] != path_digest(draft):
        raise CVError(
            "Review is stale: draft file changed. Regenerate review and obtain new approval"
        )
    if review["preferences_sha256"] != path_digest(PREFERENCES_DRAFT):
        raise CVError("Review is stale: preferences changed. Regenerate review")
    current_preferences_draft = validate_preferences(load_yaml(PREFERENCES_DRAFT))
    if review["preferences_snapshot"] != current_preferences_draft:
        raise CVError("Review preferences snapshot differs from draft. Regenerate review")
    current_profile = validate_profile(load_yaml(draft))
    if review["profile_snapshot"] != current_profile:
        raise CVError("Review snapshot differs from draft. Update draft and regenerate the review")
    if review["summary"] != reviewed_summary(current_profile):
        raise CVError("Review summary was modified or is stale. Regenerate the review")
    if review["decision"] not in ("pending", "approved", "changes_requested"):
        raise CVError("Review decision must be pending, approved, or changes_requested")
    return cast(dict[str, Any], review)


def approve(
    draft: Path | None = None, review_path: Path | None = None, *, replace: bool = False
) -> None:
    if draft is None:
        draft = DRAFT
    if review_path is None:
        review_path = REVIEW
    review = validate_review(load_yaml(review_path), draft)
    if review["decision"] != "approved":
        raise CVError("Human gate blocked: decision is not approved")
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise CVError("Human gate blocked: reviewer must identify the human approval")
    timestamp = review.get("reviewed_at")
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise CVError("Human gate blocked: reviewed_at must be recorded")
    try:
        when = dt.datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise CVError("Human gate blocked: reviewed_at must be ISO-8601") from exc
    if when.tzinfo is None or when.utcoffset() is None:
        raise CVError("Human gate blocked: reviewed_at must include a timezone")
    # Promote the reviewed snapshots, never a later reread of mutable drafts.
    profile = validate_profile(copy.deepcopy(review["profile_snapshot"]), for_approval=True)
    preferences = validate_preferences(copy.deepcopy(review["preferences_snapshot"]))
    unresolved = unresolved_paths(profile)
    if (unresolved or profile.get("open_questions")) and review.get(
        "acknowledge_exclusions"
    ) is not True:
        raise CVError("Human must acknowledge exclusion of unresolved/unverified information")
    previous_hash = profile.get("base_profile_sha256")
    previous_preferences_hash = preferences.get("base_preferences_sha256")
    if PREFERENCES.exists():
        if not replace:
            raise CVError("Approved profile exists; use `approve --replace` for an update")
        if previous_preferences_hash != path_digest(PREFERENCES):
            raise CVError("Approved preferences changed since draft creation; review again")
    elif previous_preferences_hash is not None:
        raise CVError("Draft expects existing approved preferences, but they are missing")
    if PROFILE.exists():
        if not replace:
            raise CVError(
                "Approved profile exists; use `approve --replace` for an authorized update"
            )
        if previous_hash != path_digest(PROFILE):
            raise CVError(
                "Approved profile changed since draft creation. Reconcile before replacing"
            )
        backup = (
            DATA
            / "history"
            / (
                f"profile-{dt.datetime.now(dt.UTC).strftime('%Y%m%dT%H%M%S%fZ')}-"
                f"{path_digest(PROFILE)[:12]}.yaml"
            )
        )
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROFILE, backup)
        print(f"Backed up previous approved profile to {backup}")
    elif previous_hash is not None:
        raise CVError("Draft expects an existing approved profile, but it is missing")
    if (
        path_digest(draft) != review["draft_sha256"]
        or path_digest(PREFERENCES_DRAFT) != review["preferences_sha256"]
    ):
        raise CVError("Draft changed during approval; regenerate review and obtain approval again")
    # Copy every review artifact before promotion; copy failures leave active drafts intact.
    archived_sources: list[Path] = []
    if draft == DRAFT and review_path == REVIEW:
        archive_dir = DATA / "history"
        archive_dir.mkdir(parents=True, exist_ok=True)
        suffix = f"{dt.datetime.now(dt.UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{path_digest(draft)[:12]}"
        for source, label in (
            (draft, "draft"),
            (PREFERENCES_DRAFT, "preferences-draft"),
            (review_path, "review"),
        ):
            shutil.copy2(source, archive_dir / f"{label}-{suffix}.yaml")
            archived_sources.append(source)
    approved_preferences = copy.deepcopy(preferences)
    approved_preferences.pop("base_preferences_sha256", None)
    write_yaml_pair(PROFILE, profile, PREFERENCES, approved_preferences)
    for source in archived_sources:
        source.unlink()
    if archived_sources:
        print(f"Review and drafts archived under {DATA / 'history'}")
    print(f"Approved profile: {PROFILE}")
    if unresolved:
        print(f"Excluded: {len(unresolved)} unverified paths must stay out of every CV")


def validate_resume_basic(data: Any) -> dict[str, Any]:
    """Fast preflight. Actual RenderCV validation happens during `rendercv render`."""
    if not isinstance(data, dict) or not isinstance(data.get("cv"), dict):
        raise CVError("RenderCV YAML must contain a cv: mapping")
    unknown = set(data) - {"cv", "design", "locale", "settings"}
    if unknown:
        raise CVError(f"Unknown RenderCV top-level keys: {', '.join(sorted(map(str, unknown)))}")
    cv = data["cv"]
    if not isinstance(cv.get("name"), str) or not cv["name"].strip():
        raise CVError("CV must include a nonempty cv.name")
    if not isinstance(cv.get("sections"), dict) or not cv["sections"]:
        raise CVError("CV must include nonempty cv.sections")
    for name, records in cv["sections"].items():
        if not isinstance(name, str) or not isinstance(records, list) or not records:
            raise CVError(f"Section {name!r} must contain a nonempty list")
        if any(not isinstance(entry, (str, dict)) for entry in records):
            raise CVError(f"Section {name!r} has invalid entry types")
    if any(
        key in data and not isinstance(data[key], dict) for key in ("design", "locale", "settings")
    ):
        raise CVError("design, locale and settings must be mappings when present")
    return cast(dict[str, Any], data)


def require_approved_for_build(source: Path, *, example: bool) -> None:
    if example:
        if source.resolve() != (ROOT / "templates" / "rendercv.example.yaml").resolve():
            raise CVError("--example only permits the committed synthetic rendercv.example.yaml")
        return
    if not PROFILE.is_file():
        raise CVError("No approved data/profile.yaml. Finish human review and approve first")
    validate_profile(load_yaml(PROFILE), for_approval=True)
    if not source.resolve().is_relative_to((ROOT / "resumes").resolve()):
        raise CVError("Real CV YAML must be under resumes/ (private, Git-ignored)")


def pdf_report(pdf: Path, *, max_pages: int = 2, target_pages: int | None = None) -> dict[str, Any]:
    if max_pages < 1:
        raise CVError("--max-pages must be >= 1")
    if target_pages is not None and target_pages < 1:
        raise CVError("target_pages must be >= 1")
    if not pdf.is_file():
        raise CVError(f"PDF not found: {pdf}")
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:
        raise CVError("Missing pypdf. Run `python scripts/bootstrap.py`.") from exc
    try:
        reader = PdfReader(str(pdf), strict=True)
        texts: list[str] = []
        links = 0
        for page in reader.pages:
            texts.append(page.extract_text() or "")
            for reference in page.get("/Annots", []) or []:
                annotation = reference.get_object()
                if annotation.get("/Subtype") == "/Link":
                    links += 1
    except (PdfReadError, OSError, KeyError, ValueError, TypeError) as exc:
        raise CVError(f"PDF cannot be inspected: {exc}") from exc
    warnings: list[str] = []
    if not texts:
        warnings.append("PDF has zero pages")
    elif any(len(text.strip()) < 20 for text in texts):
        warnings.append("At least one page has insufficient extractable text")
    if len(texts) > max_pages:
        warnings.append(f"PDF has {len(texts)} pages (requested max {max_pages})")
    if target_pages is not None and len(texts) != target_pages:
        warnings.append(f"PDF has {len(texts)} pages (requested exactly {target_pages})")
    return {
        "pdf": str(pdf),
        "pages": len(texts),
        "target_pages": target_pages,
        "characters": sum(len(text) for text in texts),
        "link_annotations": links,
        "warnings": warnings,
        "passed": not warnings,
        "limitations": (
            "Structural checks only; requires agent visual PNG review, factual claim check, "
            "and human PDF approval. ATS acceptance is not guaranteed."
        ),
    }


def publish_build(package: Path, destination: Path) -> None:
    """Publish a complete build; preserve old output even if rollback itself fails."""
    backup_root: Path | None = None
    if destination.exists():
        backup_root = Path(tempfile.mkdtemp(prefix=".previous_", dir=destination.parent))
        if not backup_root.resolve().is_relative_to(destination.parent.resolve()):
            raise CVError("Unexpected build backup path")
        destination.rename(backup_root / "artifacts")
    try:
        package.rename(destination)
    except OSError as publish_error:
        if backup_root is not None:
            try:
                (backup_root / "artifacts").rename(destination)
            except OSError as recovery_error:
                raise CVError(
                    f"Output recovery failed; previous build is safe at {backup_root}"
                ) from recovery_error
            backup_root.rmdir()
        raise publish_error
    if backup_root is not None:
        shutil.rmtree(backup_root)


def publish_artifacts(stage: Path, destination: Path, report: dict[str, Any]) -> None:
    """Copy into the destination parent to inherit its ACL before publishing."""
    package = destination.parent / f".publish_{stage.name}"
    package.mkdir()
    try:
        for item in stage.iterdir():
            if item.suffix.lower() in (".pdf", ".png"):
                shutil.copy2(item, package / item.name)
        report["pdf"] = str(destination / "resume.pdf")
        write_atomic(package / "audit.json", json.dumps(report, indent=2) + "\n")
        publish_build(package, destination)
    finally:
        if package.exists():
            if not package.resolve().is_relative_to(destination.parent.resolve()):
                raise CVError("Unexpected build package path")
            shutil.rmtree(package)


def build(
    source: Path,
    *,
    example: bool = False,
    max_pages: int | None = None,
    theme: str | None = None,
) -> Path:
    source = source.resolve()
    validate_resume_basic(load_yaml(source))
    require_approved_for_build(source, example=example)
    preferences = current_preferences(example=example)
    chosen_theme = theme or preferences["resume"]["theme"]
    if chosen_theme not in THEMES:
        raise CVError(f"Unknown theme {chosen_theme!r}; run `python scripts/cv.py themes`")
    language = preferences["resume"]["language"]
    page_target = max_pages if max_pages is not None else int(preferences["resume"]["target_pages"])
    if page_target < 1:
        raise CVError("--max-pages must be >= 1")
    command = get_rendercv_command()
    if not command.is_file():
        raise CVError("RenderCV executable not found. Run `python scripts/bootstrap.py`.")
    if not example and (
        source.suffix != ".yaml"
        or re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*_cv", source.stem) is None
    ):
        raise CVError("Resume filenames must use lowercase snake_case ending in _cv.yaml")
    destination = ROOT / "output" / source.stem
    if destination.exists():
        audit_path = destination / "audit.json"
        if not audit_path.is_file():
            raise CVError("Output exists without source metadata; preserve it before rebuilding")
        try:
            prior_source = json.loads(audit_path.read_text(encoding="utf-8")).get("source")
        except (ValueError, AttributeError) as exc:
            raise CVError(
                "Existing output metadata is invalid; preserve it before rebuilding"
            ) from exc
        if prior_source != source.relative_to(ROOT).as_posix():
            raise CVError("Output name collision: use a unique resume filename")
    (ROOT / "output").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".render-", dir=ROOT / "output") as tmp:
        stage = Path(tmp)
        pdf = stage / "resume.pdf"
        result = subprocess.run(
            [
                str(command),
                "render",
                str(source),
                "--quiet",
                "--pdf-path",
                str(pdf),
                "--png-path",
                str(stage / "preview.png"),
                "--typst-path",
                str(stage / "resume.typ"),
                "--dont-generate-markdown",
                "--dont-generate-html",
                "--design.theme",
                chosen_theme,
                "--locale.language",
                language,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
            check=False,
        )
        if result.returncode != 0:
            raise CVError(f"RenderCV failed:\n{result.stdout}\n{result.stderr}")
        if not pdf.is_file():
            raise CVError("RenderCV exited successfully but produced no PDF")
        report = pdf_report(pdf, max_pages=page_target, target_pages=page_target)
        report["source"] = source.relative_to(ROOT).as_posix()
        report["theme"] = chosen_theme
        report["language"] = language
        report["theme_override"] = theme is not None
        report["page_target_override"] = max_pages is not None
        previews = list(stage.glob("*.png"))
        if not previews:
            report["warnings"].append("No preview PNG produced by RenderCV")
            report["passed"] = False
        elif len(previews) != report["pages"]:
            report["warnings"].append("Preview PNG count does not match PDF page count")
            report["passed"] = False
        for preview in previews:
            with preview.open("rb") as stream:
                header = stream.read(24)
            if (
                len(header) < 24
                or header[:8] != b"\x89PNG\r\n\x1a\n"
                or header[12:16] != b"IHDR"
                or int.from_bytes(header[16:20]) == 0
                or int.from_bytes(header[20:24]) == 0
            ):
                report["warnings"].append(f"Invalid preview PNG: {preview.name}")
                report["passed"] = False
        report["previews"] = sorted(item.name for item in previews)
        if not report["passed"]:
            failed = ROOT / "output" / "failed" / source.stem
            failed.mkdir(parents=True, exist_ok=True)
            attempt = failed / f"attempt_{stage.name.removeprefix('.render-')}"
            attempt.mkdir()
            for item in stage.iterdir():
                if item.suffix.lower() in (".pdf", ".png"):
                    shutil.copy2(item, attempt / item.name)
            report["pdf"] = str(attempt / "resume.pdf")
            write_atomic(attempt / "audit.json", json.dumps(report, indent=2) + "\n")
            raise CVError(f"Build audit failed; inspect {attempt}: {report['warnings']}")
        publish_artifacts(stage, destination, report)
    print(f"Rendered: {destination}")
    print("Agent must visually inspect every preview PNG and request human final approval.")
    return destination


def doctor() -> None:
    import importlib.metadata as metadata

    expected = {"rendercv": "2.8", "pyyaml": "6.0.3", "jsonschema": "4.25.1", "pypdf": "6.2.0"}
    problems = []
    for name, version in expected.items():
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            installed = "MISSING"
        print(f"{name}: {installed} (expected {version})")
        if installed != version:
            problems.append(name)
    if Path(sys.prefix).resolve() != VENV.resolve():
        problems.append(".venv interpreter")
    command = get_rendercv_command()
    if not command.is_file():
        problems.append("rendercv CLI")
    if problems:
        raise CVError("Doctor found problems: " + ", ".join(problems) + ". Run bootstrap.py")
    check = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True)
    if check.returncode != 0:
        raise CVError("pip check failed:\n" + check.stdout + check.stderr)
    print("Environment OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Verify runtime environment")
    start = sub.add_parser("begin-update", help="Create a guarded draft from the approved profile")
    start.add_argument("--replace", action="store_true", help="Explicitly replace existing draft")
    review = sub.add_parser("review", help="Create an immutable-snapshot human review artifact")
    review.add_argument("--replace", action="store_true", help="Regenerate stale review")
    approve_command = sub.add_parser(
        "approve", help="Promote a human-approved draft into canonical profile"
    )
    approve_command.add_argument(
        "--replace", action="store_true", help="Replace existing approved profile with backup"
    )
    validate = sub.add_parser("validate", help="Validate YAML structure")
    validate.add_argument(
        "--kind", required=True, choices=("profile", "preferences", "review", "resume")
    )
    validate.add_argument("--input", type=Path, required=True)
    build_cmd = sub.add_parser("build", help="Render PDF + PNG with approval gate")
    build_cmd.add_argument("--input", type=Path, required=True)
    build_cmd.add_argument("--example", action="store_true", help="Only render synthetic example")
    build_cmd.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Required PDF page count for this build only (overrides target_pages)",
    )
    build_cmd.add_argument("--theme", choices=THEMES, help="Temporary build-only override")
    sub.add_parser("themes", help="List locally available official theme PDF examples")
    audit = sub.add_parser("audit", help="Inspect already generated PDF without rendering")
    audit.add_argument("--pdf", type=Path, required=True)
    audit.add_argument("--max-pages", type=int, default=2, help="Page upper bound (default: 2)")
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            doctor()
        elif args.command == "begin-update":
            begin_update(replace=args.replace)
        elif args.command == "review":
            prepare_review(replace=args.replace)
        elif args.command == "approve":
            approve(replace=args.replace)
        elif args.command == "validate":
            data = load_yaml(args.input)
            if args.kind == "profile":
                validate_profile(data)
            elif args.kind == "preferences":
                validate_preferences(data)
            elif args.kind == "review":
                validate_review(data, DRAFT)
            else:
                validate_resume_basic(data)
            print(f"YAML preflight OK: {args.input} ({args.kind})")
        elif args.command == "build":
            build(args.input, example=args.example, max_pages=args.max_pages, theme=args.theme)
        elif args.command == "themes":
            return list_themes()
        elif args.command == "audit":
            report = pdf_report(args.pdf, max_pages=args.max_pages)
            print(json.dumps(report, indent=2))
            if not report["passed"]:
                return 1
        else:
            parser.error("Unknown command")
    except (CVError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        delegated = reexec_if_needed(sys.argv[1:])
    except CVError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    if delegated is not None:
        raise SystemExit(delegated)
    raise SystemExit(main())
