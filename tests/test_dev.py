from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts import dev


@pytest.fixture(autouse=True)
def isolated_dev_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev, "ROOT", tmp_path)


def test_dev_fails_without_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev, "PYTHON", tmp_path / "missing-python")
    assert dev.run_checks("check") == 1


def test_dev_checks_all_commands_in_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "python").touch()
    (tmp_path / ("ruff.exe" if os.name == "nt" else "ruff")).touch()
    (tmp_path / ("basedpyright.exe" if os.name == "nt" else "basedpyright")).touch()
    monkeypatch.setattr(dev, "SCRIPTS", tmp_path)
    monkeypatch.setattr(dev, "PYTHON", tmp_path / "python")
    executed: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "-c" in argv:
            return subprocess.CompletedProcess(argv, 0, "3.14\n", "")
        executed.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(dev.subprocess, "run", fake_run)
    assert dev.run_checks("check") == 0
    assert len(executed) == 4
    assert executed[0][1] == "check"
    assert Path(executed[2][0]).stem == "basedpyright"
    assert executed[2][-2:] == ["--pythonversion", "3.14"]
    assert executed[3][2] == "pytest"


def test_dev_stops_on_lint_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "python").touch()
    (tmp_path / ("ruff.exe" if os.name == "nt" else "ruff")).touch()
    monkeypatch.setattr(dev, "SCRIPTS", tmp_path)
    monkeypatch.setattr(dev, "PYTHON", tmp_path / "python")
    seen: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 2)

    monkeypatch.setattr(dev.subprocess, "run", fake_run)
    assert dev.run_checks("lint") == 2
    assert len(seen) == 1


def test_dev_missing_optional_tool_is_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "python").touch()
    monkeypatch.setattr(dev, "SCRIPTS", tmp_path)
    monkeypatch.setattr(dev, "PYTHON", tmp_path / "python")
    assert dev.run_checks("type") == 1


@pytest.mark.parametrize("version_ok", [False, True])
def test_typecheck_probe_failure_is_actionable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version_ok: bool
) -> None:
    (tmp_path / "python").touch()
    (tmp_path / ("basedpyright.exe" if os.name == "nt" else "basedpyright")).touch()
    monkeypatch.setattr(dev, "PYTHON", tmp_path / "python")
    monkeypatch.setattr(dev, "SCRIPTS", tmp_path)

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if version_ok:
            raise OSError("not executable")
        return subprocess.CompletedProcess(argv, 1, "", "unavailable")

    monkeypatch.setattr(dev.subprocess, "run", run)
    assert dev.main(["type"]) == 1


def test_coverage_generates_reports_in_private_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python = tmp_path / "python"
    python.touch()
    monkeypatch.setattr(dev, "PYTHON", python)
    commands: list[list[str]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(dev.subprocess, "run", run)
    assert dev.main(["coverage"]) == 0
    assert [args[3] for args in commands] == ["run", "report", "json", "html"]
    report = Path(commands[2][-1])
    assert report.name == "coverage.json"
    assert report.parent.parent == tmp_path / "output/quality/runs"
    assert Path(commands[3][-1]) == report.parent / "html"


def test_each_run_isolates_temp_cache_and_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python = tmp_path / "python"
    python.touch()
    monkeypatch.setattr(dev, "PYTHON", python)
    calls: list[tuple[list[str], dict[str, str]]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs["env"]))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(dev.subprocess, "run", run)
    assert dev.run_checks("test") == dev.run_checks("test") == 0
    first_args, first_env = calls[0]
    second_args, second_env = calls[1]
    first_temp = Path(first_args[first_args.index("--basetemp") + 1])
    second_temp = Path(second_args[second_args.index("--basetemp") + 1])
    assert first_temp != second_temp
    for argv, env in calls:
        run_root = Path(env["COVERAGE_FILE"]).parent
        assert Path(argv[argv.index("--basetemp") + 1]).parent == run_root
        assert f"cache_dir={run_root / 'pytest_cache'}" in argv
        assert Path(env["RUFF_CACHE_DIR"]).parent == run_root
        assert Path(env["RESUME_PILOT_TEST_ARTIFACTS"]).parent == run_root
    assert first_env["COVERAGE_FILE"] != second_env["COVERAGE_FILE"]


def test_real_pytest_ignores_unusable_shared_cache_and_temp_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Files at the old directory paths reproduce unusable shared locations portably.
    (tmp_path / ".pytest_cache").write_text("preserve shared cache", encoding="utf-8")
    blocked_temp = tmp_path / "blocked_temp"
    blocked_temp.write_text("preserve shared temp", encoding="utf-8")
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(blocked_temp))
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\nfilterwarnings = ["error"]\n', encoding="utf-8"
    )
    (tmp_path / "test_temp.py").write_text(
        'def test_temp(tmp_path):\n    (tmp_path / "ok.txt").write_bytes(b"ok")\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(dev, "PYTHON", Path(sys.executable))
    assert dev.run_checks("test") == 0
    assert dev.run_checks("test") == 0
    assert (tmp_path / ".pytest_cache").read_text(encoding="utf-8") == "preserve shared cache"
    assert blocked_temp.read_text(encoding="utf-8") == "preserve shared temp"
