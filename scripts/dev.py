"""Cross-platform development checks in the existing .venv (no activation needed)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin")
PYTHON = SCRIPTS / ("python.exe" if os.name == "nt" else "python")


def run_checks(task: str) -> int:
    if not PYTHON.is_file():
        print("ERROR: Missing venv. Run `python scripts/bootstrap.py --dev`", file=sys.stderr)
        return 1
    ruff = SCRIPTS / ("ruff.exe" if os.name == "nt" else "ruff")
    basedpyright = SCRIPTS / ("basedpyright.exe" if os.name == "nt" else "basedpyright")
    # Fresh paths avoid sharing owner-only pytest caches/temp roots across accounts.
    run_root = ROOT / "output" / "quality" / "runs" / uuid.uuid4().hex
    try:
        run_root.mkdir(parents=True)
    except OSError as exc:
        print(f"ERROR: Cannot create quality output: {exc}", file=sys.stderr)
        return 1
    print(f"Quality output: {run_root}", flush=True)
    child_env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "RUFF_CACHE_DIR": str(run_root / "ruff_cache"),
        "COVERAGE_FILE": str(run_root / ".coverage"),
        "RESUME_PILOT_TEST_ARTIFACTS": str(run_root / "integration"),
    }
    pytest_args = [
        "-q",
        "--basetemp",
        str(run_root / "tmp"),
        "-o",
        f"cache_dir={run_root / 'pytest_cache'}",
    ]
    tasks = {
        "lint": [[str(ruff), "check", "."], [str(ruff), "format", "--check", "."]],
        "type": [[str(basedpyright), "--warnings", "--pythonpath", str(PYTHON)]],
        "test": [[str(PYTHON), "-m", "pytest", *pytest_args]],
        "coverage": [
            [str(PYTHON), "-m", "coverage", "run", "-m", "pytest", *pytest_args],
            [str(PYTHON), "-m", "coverage", "report"],
            [str(PYTHON), "-m", "coverage", "json", "-o", str(run_root / "coverage.json")],
            [str(PYTHON), "-m", "coverage", "html", "-d", str(run_root / "html")],
        ],
        "format": [[str(ruff), "format", "."]],
    }
    commands = tasks["lint"] + tasks["type"] + tasks["test"] if task == "check" else tasks[task]
    for args in commands:
        if not Path(args[0]).is_file():
            print(
                "ERROR: Dev tool missing. Run `python scripts/bootstrap.py --dev`",
                file=sys.stderr,
            )
            return 1
        print("Running:", " ".join(args), flush=True)
        try:
            if args[0] == str(basedpyright):
                version = subprocess.run(
                    [
                        str(PYTHON),
                        "-c",
                        "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    env=child_env,
                    check=False,
                )
                if version.returncode or not version.stdout.strip():
                    print("ERROR: Cannot identify .venv Python version", file=sys.stderr)
                    return 1
                args = [*args, "--pythonversion", version.stdout.strip()]
            result = subprocess.run(
                args,
                cwd=ROOT,
                check=False,
                env=child_env,
            )
        except OSError as exc:
            print(f"ERROR: Could not run development tool: {exc}", file=sys.stderr)
            return 1
        if result.returncode != 0:
            return result.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=("check", "lint", "type", "test", "coverage", "format"))
    return run_checks(parser.parse_args(argv).task)


if __name__ == "__main__":
    raise SystemExit(main())
