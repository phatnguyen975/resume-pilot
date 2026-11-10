from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts import bootstrap


@pytest.fixture
def bootstrap_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "requirements.txt").write_text("rendercv[full]==2.8\nPyYAML==6.0.3\n")
    (tmp_path / "requirements-dev.txt").write_text("-r requirements.txt\npytest==8.4.2\n")
    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    monkeypatch.setattr(bootstrap, "VENV", tmp_path / ".venv")
    monkeypatch.setattr(bootstrap, "STAMP", tmp_path / ".venv" / ".resume-pilot-bootstrap.json")
    return tmp_path


def test_requirements_tree_includes_and_hashes(bootstrap_workspace: Path) -> None:
    pins, digest = bootstrap.requirements_tree(bootstrap_workspace / "requirements-dev.txt")
    assert pins == {"rendercv": "2.8", "pyyaml": "6.0.3", "pytest": "8.4.2"}
    assert len(digest) == 64
    (bootstrap_workspace / "requirements.txt").write_text(
        "rendercv[full]==2.8\nPyYAML==6.0.3\n# new"
    )
    assert bootstrap.requirements_tree(bootstrap_workspace / "requirements-dev.txt")[1] != digest


@pytest.mark.parametrize(
    "bad_line",
    ["rendercv>=2.8", "rendercv", "--extra-index-url https://example.com", "rendercv=="],
)
def test_unpinned_requirements_rejected(bootstrap_workspace: Path, bad_line: str) -> None:
    target = bootstrap_workspace / "requirements.txt"
    target.write_text(bad_line + "\n")
    with pytest.raises(bootstrap.BootstrapError, match="Unsupported"):
        bootstrap.requirements_tree(target)


def test_requirements_circular_include_rejected(bootstrap_workspace: Path) -> None:
    (bootstrap_workspace / "requirements.txt").write_text("-r requirements-dev.txt")
    with pytest.raises(bootstrap.BootstrapError, match="Circular"):
        bootstrap.requirements_tree(bootstrap_workspace / "requirements-dev.txt")


def test_requirements_cannot_escape_repo(bootstrap_workspace: Path) -> None:
    with pytest.raises(bootstrap.BootstrapError, match="inside this repo"):
        bootstrap.requirements_tree(bootstrap_workspace.parent / "secrets.txt")


def test_conflicting_requirements_rejected(bootstrap_workspace: Path) -> None:
    target = bootstrap_workspace / "requirements.txt"
    target.write_text("rendercv==2.8\nrendercv==2.7\n")
    with pytest.raises(bootstrap.BootstrapError, match="Conflicting"):
        bootstrap.requirements_tree(target)


def test_dependencies_ok_when_installed_and_pip_check_passes(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "installed_versions", lambda python: {"rendercv": "2.8"})
    monkeypatch.setattr(
        bootstrap,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "", ""),
    )
    assert bootstrap.dependencies_ok(Path("python"), {"rendercv": "2.8"})
    assert not bootstrap.dependencies_ok(Path("python"), {"rendercv": "2.9"})


def test_dependencies_fail_on_pip_check(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "installed_versions", lambda python: {"rendercv": "2.8"})
    monkeypatch.setattr(
        bootstrap,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, "", "bad"),
    )
    assert not bootstrap.dependencies_ok(Path("python"), {"rendercv": "2.8"})


def test_bootstrap_noop_does_not_reinstall(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    venv_python = bootstrap.venv_python(bootstrap.VENV)
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("fake")
    _pins, fingerprint = bootstrap.requirements_tree(bootstrap.ROOT / "requirements.txt")
    bootstrap.STAMP.write_text(json.dumps({"fingerprint": fingerprint}))
    monkeypatch.setattr(bootstrap, "verify_venv", lambda python: None)
    monkeypatch.setattr(bootstrap, "dependencies_ok", lambda python, pins: True)
    monkeypatch.setattr(bootstrap, "rendercv_ok", lambda python: True)
    monkeypatch.setattr(
        bootstrap,
        "run",
        lambda argv, **kwargs: pytest.fail("pip must not run when stamp and state are valid"),
    )
    bootstrap.bootstrap()


def test_bootstrap_repairs_missing_dependency_without_upgrade_flag(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    venv_python = bootstrap.venv_python(bootstrap.VENV)
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("fake")
    monkeypatch.setattr(bootstrap, "verify_venv", lambda python: None)
    statuses = iter([False, True])
    monkeypatch.setattr(bootstrap, "dependencies_ok", lambda python, pins: next(statuses))
    monkeypatch.setattr(bootstrap, "rendercv_ok", lambda python: True)
    monkeypatch.setattr(bootstrap, "smoke_render", lambda: None)
    commands: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(bootstrap, "run", fake_run)
    bootstrap.bootstrap()
    assert len(commands) == 1
    assert commands[0][1:4] == ["-m", "pip", "install"]
    assert "--upgrade" not in commands[0]
    assert bootstrap.STAMP.is_file()


def test_bootstrap_refuses_corrupt_venv_without_deletion(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootstrap.VENV.mkdir()
    marker = bootstrap.VENV / "some-user-data.txt"
    marker.write_text("preserve")
    with pytest.raises(bootstrap.BootstrapError, match="no Python executable"):
        bootstrap.bootstrap()
    assert marker.read_text() == "preserve"


def test_bootstrap_dry_run_avoids_modification(bootstrap_workspace: Path) -> None:
    bootstrap.bootstrap(dry_run=True)
    assert not bootstrap.VENV.exists()


def test_verify_venv_rejects_wrong_prefix(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, json.dumps(["/wrong/venv", [3, 13]]), "")

    monkeypatch.setattr(bootstrap, "run", fake_run)
    with pytest.raises(bootstrap.BootstrapError, match="different directory"):
        bootstrap.verify_venv(Path("python"))


def test_failed_pip_does_not_write_stamp(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    venv_python = bootstrap.venv_python(bootstrap.VENV)
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("fake")
    monkeypatch.setattr(bootstrap, "verify_venv", lambda python: None)
    monkeypatch.setattr(bootstrap, "dependencies_ok", lambda python, pins: False)
    monkeypatch.setattr(bootstrap, "rendercv_ok", lambda python: False)
    monkeypatch.setattr(
        bootstrap,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, "", "offline"),
    )
    with pytest.raises(bootstrap.BootstrapError, match="pip install failed"):
        bootstrap.bootstrap()
    assert not bootstrap.STAMP.exists()


def test_bootstrap_skips_pip_when_packages_present_without_stamp(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python = bootstrap.venv_python()
    python.parent.mkdir(parents=True)
    python.write_text("fake")
    monkeypatch.setattr(bootstrap, "verify_venv", lambda python: None)
    monkeypatch.setattr(bootstrap, "dependencies_ok", lambda python, pins: True)
    monkeypatch.setattr(bootstrap, "rendercv_ok", lambda python: True)
    monkeypatch.setattr(bootstrap, "smoke_render", lambda: None)
    monkeypatch.setattr(bootstrap, "run", lambda argv, **kwargs: pytest.fail("No pip needed"))
    bootstrap.bootstrap()
    assert bootstrap.STAMP.is_file()


def test_bootstrap_dry_run_with_existing_venv_is_safe(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python = bootstrap.venv_python()
    python.parent.mkdir(parents=True)
    python.write_text("fake")
    monkeypatch.setattr(bootstrap, "verify_venv", lambda python: None)
    monkeypatch.setattr(bootstrap, "dependencies_ok", lambda python, pins: False)
    monkeypatch.setattr(bootstrap, "rendercv_ok", lambda python: False)
    bootstrap.bootstrap(dry_run=True)
    assert not bootstrap.STAMP.exists()


def test_smoke_render_missing_pdf_raises(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(bootstrap, "run", fake_run)
    with pytest.raises(bootstrap.BootstrapError, match="sample PDF"):
        bootstrap.smoke_render()


def test_smoke_render_missing_png_raises(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        path = Path(argv[argv.index("--pdf-path") + 1])
        path.write_bytes(b"fake")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(bootstrap, "run", fake_run)
    with pytest.raises(bootstrap.BootstrapError, match="preview PNG"):
        bootstrap.smoke_render()


def test_smoke_render_nonzero_exit_raises(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        bootstrap,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, "", "error"),
    )
    with pytest.raises(bootstrap.BootstrapError, match="smoke render failed"):
        bootstrap.smoke_render()


def test_validate_venv_ok_and_missing_pip(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = json.dumps([str(bootstrap.VENV), [3, 12]])
    statuses = iter([0, 0, 0, 1])

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, next(statuses), expected, "missing")

    monkeypatch.setattr(bootstrap, "run", fake_run)
    bootstrap.verify_venv(Path("python"))
    with pytest.raises(bootstrap.BootstrapError, match="pip is unavailable"):
        bootstrap.verify_venv(Path("python"))


def test_rendercv_ok_checks_version_in_stderr(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = bootstrap.venv_command("rendercv")
    exe.parent.mkdir(parents=True)
    exe.touch()
    monkeypatch.setattr(
        bootstrap,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "", "RenderCV v2.8"),
    )
    python = bootstrap.venv_python()
    assert bootstrap.rendercv_ok(python)


def test_run_raises_when_executable_missing(bootstrap_workspace: Path) -> None:
    with pytest.raises(bootstrap.BootstrapError, match="Could not execute"):
        bootstrap.run(["/definitely/not/present/resume-pilot-tool"])


def test_install_failure_after_pip_check_does_not_stamp(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python = bootstrap.venv_python()
    python.parent.mkdir(parents=True)
    python.write_text("fake")
    monkeypatch.setattr(bootstrap, "verify_venv", lambda python: None)
    monkeypatch.setattr(bootstrap, "dependencies_ok", lambda python, pins: False)
    monkeypatch.setattr(bootstrap, "rendercv_ok", lambda python: True)
    monkeypatch.setattr(
        bootstrap,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "", ""),
    )
    with pytest.raises(bootstrap.BootstrapError, match="inconsistent"):
        bootstrap.bootstrap()
    assert not bootstrap.STAMP.exists()


def test_bootstrap_help_only_contains_setup_options(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exception:
        bootstrap.main(["--help"])
    assert exception.value.code == 0
    help_text = capsys.readouterr().out
    assert "--dev" in help_text
    assert "--dry-run" in help_text


def test_bootstrap_does_not_touch_examples(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python = bootstrap.venv_python()
    python.parent.mkdir(parents=True)
    python.write_text("fake")
    monkeypatch.setattr(bootstrap, "verify_venv", lambda python: None)
    monkeypatch.setattr(bootstrap, "dependencies_ok", lambda python, pins: True)
    monkeypatch.setattr(bootstrap, "rendercv_ok", lambda python: True)
    monkeypatch.setattr(bootstrap, "smoke_render", lambda: None)
    bootstrap.bootstrap()
    assert not (bootstrap_workspace / "examples").exists()


@pytest.mark.parametrize("nested_first", [False, True])
def test_conflicting_versions_across_includes_are_rejected(
    bootstrap_workspace: Path, nested_first: bool
) -> None:
    parts = ["-r requirements.txt", "rendercv==2.7"]
    if not nested_first:
        parts.reverse()
    (bootstrap_workspace / "requirements-dev.txt").write_text("\n".join(parts), encoding="utf-8")
    with pytest.raises(bootstrap.BootstrapError, match="Conflicting"):
        bootstrap.requirements_tree(bootstrap_workspace / "requirements-dev.txt")


def test_requirements_invalid_encoding_is_actionable(bootstrap_workspace: Path) -> None:
    path = bootstrap_workspace / "requirements.txt"
    path.write_bytes(b"\xff")
    with pytest.raises(bootstrap.BootstrapError, match="Cannot read requirements"):
        bootstrap.requirements_tree(path)


def test_requirements_missing_file_is_actionable(bootstrap_workspace: Path) -> None:
    with pytest.raises(bootstrap.BootstrapError, match="Missing requirements"):
        bootstrap.requirements_tree(bootstrap_workspace / "missing.txt")


def test_subprocess_utf8_roundtrip() -> None:
    result = bootstrap.run([sys.executable, "-c", "print(chr(0x2713))"])
    assert result.returncode == 0
    assert result.stdout.strip() == chr(0x2713)


def test_installed_packages_and_venv_can_be_inspected() -> None:
    versions = bootstrap.installed_versions(Path(sys.executable))
    assert versions["rendercv"] == "2.8"
    bootstrap.verify_venv(Path(sys.executable), Path(sys.prefix))


@pytest.mark.parametrize("stdout", ["bad json", "[]", '{"package": 3}', "null"])
def test_invalid_package_metadata_is_actionable(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch, stdout: str
) -> None:
    monkeypatch.setattr(
        bootstrap, "run", lambda argv: subprocess.CompletedProcess(argv, 0, stdout, "")
    )
    with pytest.raises(bootstrap.BootstrapError, match="Invalid package metadata"):
        bootstrap.installed_versions(Path("python"))


def test_failed_metadata_command_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bootstrap, "run", lambda argv: subprocess.CompletedProcess(argv, 1, "", "broken")
    )
    with pytest.raises(bootstrap.BootstrapError, match="Cannot inspect"):
        bootstrap.installed_versions(Path("python"))


@pytest.mark.parametrize("stdout", ["bad json", "[]", "[null, [3, 14]]", '["path", "3.14"]'])
def test_invalid_interpreter_metadata_is_actionable(
    monkeypatch: pytest.MonkeyPatch, stdout: str
) -> None:
    monkeypatch.setattr(
        bootstrap, "run", lambda argv: subprocess.CompletedProcess(argv, 0, stdout, "")
    )
    with pytest.raises(bootstrap.BootstrapError, match="Could not identify"):
        bootstrap.verify_venv(Path("python"))


def test_broken_interpreter_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bootstrap, "run", lambda argv: subprocess.CompletedProcess(argv, 1, "", "broken")
    )
    with pytest.raises(bootstrap.BootstrapError, match="Broken"):
        bootstrap.verify_venv(Path("python"))


@pytest.mark.parametrize("version", ["2.80", "12.8", "2.8.1", "2.9"])
def test_rendercv_version_requires_exact_pin(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    exe = bootstrap.venv_command("rendercv")
    exe.parent.mkdir(parents=True)
    exe.touch()
    monkeypatch.setattr(
        bootstrap, "run", lambda argv: subprocess.CompletedProcess(argv, 0, version, "")
    )
    assert not bootstrap.rendercv_ok(bootstrap.venv_python())


def test_old_smoke_files_cannot_mask_missing_new_render(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = bootstrap.VENV / "smoke"
    output.mkdir(parents=True)
    (output / "sample.pdf").write_bytes(b"old pdf")
    (output / "preview.png").write_bytes(b"old png")
    monkeypatch.setattr(bootstrap, "run", lambda argv: subprocess.CompletedProcess(argv, 0, "", ""))
    with pytest.raises(bootstrap.BootstrapError, match="sample PDF"):
        bootstrap.smoke_render()
    assert (output / "sample.pdf").read_bytes() == b"old pdf"


def test_successful_smoke_publishes_requested_artifacts(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        Path(argv[argv.index("--pdf-path") + 1]).write_bytes(b"new pdf")
        Path(argv[argv.index("--png-path") + 1]).write_bytes(b"new png")
        Path(argv[argv.index("--pdf-path") + 1]).with_suffix(".typ").write_text("extra")
        assert "--quiet" in argv
        assert (
            Path(argv[argv.index("--typst-path") + 1]).parent
            == Path(argv[argv.index("--pdf-path") + 1]).parent
        )
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(bootstrap, "run", run)
    bootstrap.smoke_render()
    assert {p.name for p in (bootstrap.VENV / "smoke").iterdir()} == {"sample.pdf", "preview.png"}


def test_invalid_stamp_is_rebuilt_without_reinstall(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python = bootstrap.venv_python()
    python.parent.mkdir(parents=True)
    python.touch()
    bootstrap.STAMP.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "verify_venv", lambda python: None)
    monkeypatch.setattr(bootstrap, "dependencies_ok", lambda python, pins: True)
    monkeypatch.setattr(bootstrap, "rendercv_ok", lambda python: True)
    monkeypatch.setattr(bootstrap, "smoke_render", lambda: None)
    bootstrap.bootstrap()
    assert isinstance(json.loads(bootstrap.STAMP.read_text(encoding="utf-8")), dict)


def test_venv_creation_failure_does_not_write_stamp(
    bootstrap_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_create(_self: Any, _path: Path) -> None:
        raise OSError("ensurepip unavailable")

    monkeypatch.setattr(bootstrap.venv.EnvBuilder, "create", fail_create)
    assert bootstrap.main([]) == 1
    assert not bootstrap.STAMP.exists()
