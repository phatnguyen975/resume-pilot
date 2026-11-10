"""Idempotent, cross-platform pip + venv bootstrap (standard library only)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
STAMP = VENV / ".resume-pilot-bootstrap.json"
MIN_PYTHON = (3, 12)
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^]]+\])?==([A-Za-z0-9.!+_-]+)$")


class BootstrapError(Exception):
    """User-actionable installation failure."""


def venv_python(venv_dir: Path | None = None) -> Path:
    if venv_dir is None:
        venv_dir = VENV
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def venv_command(name: str, venv_dir: Path | None = None) -> Path:
    if venv_dir is None:
        venv_dir = VENV
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def requirements_tree(path: Path, seen: set[Path] | None = None) -> tuple[dict[str, str], str]:
    """Read pinned direct requirements and nested -r files; hash all actual content."""
    if seen is None:
        seen = set()
    path = path.resolve()
    if path in seen:
        raise BootstrapError(f"Circular/duplicate requirements include: {path}")
    if not path.is_relative_to(ROOT.resolve()):
        raise BootstrapError(f"Requirements must stay inside this repo: {path}")
    if not path.is_file():
        raise BootstrapError(f"Missing requirements file: {path}")
    seen.add(path)
    try:
        content = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise BootstrapError(f"Cannot read requirements: {path}") from exc
    pins: dict[str, str] = {}
    components = [f"{path.relative_to(ROOT)}\n{content}".encode()]
    for line in content.splitlines():
        clean = line.split("#", 1)[0].strip()
        if not clean:
            continue
        if clean.startswith(("-r ", "--requirement ")):
            nested = clean.split(maxsplit=1)[1]
            subpins, fingerprint = requirements_tree(path.parent / nested, seen)
            for package, version in subpins.items():
                if package in pins and pins[package] != version:
                    raise BootstrapError(f"Conflicting pinned versions for {package}")
                pins[package] = version
            components.append(fingerprint.encode())
            continue
        match = PIN.fullmatch(clean)
        if match is None:
            raise BootstrapError(
                f"Unsupported requirement {clean!r} in {path.name}. "
                "Use pinned == versions or -r includes."
            )
        normalized = re.sub(r"[-_.]+", "-", match.group(1)).lower()
        if normalized in pins and pins[normalized] != match.group(2):
            raise BootstrapError(f"Conflicting pinned versions for {normalized}")
        pins[normalized] = match.group(2)
    return pins, hashlib.sha256(b"\x00".join(components)).hexdigest()


def run(argv: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
            check=False,
        )
    except OSError as exc:
        raise BootstrapError(f"Could not execute {argv[0]}: {exc}") from exc


def verify_venv(python: Path, venv_dir: Path | None = None) -> None:
    if venv_dir is None:
        venv_dir = VENV
    result = run(
        [str(python), "-c", "import json,sys; print(json.dumps([sys.prefix,sys.version_info[:2]]))"]
    )
    if result.returncode != 0:
        raise BootstrapError(f"Broken .venv interpreter: {result.stderr.strip()}")
    try:
        prefix, version = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise BootstrapError("Could not identify .venv Python interpreter") from exc
    if (
        not isinstance(prefix, str)
        or not isinstance(version, list)
        or len(version) != 2
        or any(type(part) is not int for part in version)
    ):
        raise BootstrapError("Could not identify .venv Python interpreter")
    if Path(prefix).resolve() != venv_dir.resolve() or tuple(version) < MIN_PYTHON:
        raise BootstrapError(
            ".venv points to a different directory or Python < 3.12; fix it manually"
        )
    if run([str(python), "-m", "pip", "--version"]).returncode != 0:
        raise BootstrapError("pip is unavailable in .venv; repair Python/venv/ensurepip")


def installed_versions(python: Path) -> dict[str, str]:
    code = (
        "import importlib.metadata as m,json,re; "
        "print(json.dumps({re.sub(r'[-_.]+','-',d.metadata['Name']).lower():d.version "
        "for d in m.distributions() if d.metadata.get('Name')}))"
    )
    result = run([str(python), "-c", code])
    if result.returncode != 0:
        raise BootstrapError(f"Cannot inspect .venv packages: {result.stderr.strip()}")
    try:
        parsed: dict[str, str] = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise BootstrapError("Invalid package metadata in .venv") from exc
    if not isinstance(parsed, dict) or any(
        not isinstance(name, str) or not isinstance(version, str)
        for name, version in parsed.items()
    ):
        raise BootstrapError("Invalid package metadata in .venv")
    return parsed


def dependencies_ok(python: Path, pins: dict[str, str]) -> bool:
    packages = installed_versions(python)
    if any(packages.get(package) != version for package, version in pins.items()):
        return False
    return run([str(python), "-m", "pip", "check"]).returncode == 0


def rendercv_ok(python: Path) -> bool:
    command = venv_command("rendercv", python.parent.parent)
    result = run([str(command), "--version"]) if command.is_file() else None
    return (
        result is not None
        and result.returncode == 0
        and re.search(r"(?<![\d.])v?2\.8(?![\d.])", result.stdout + result.stderr) is not None
    )


def smoke_render(venv_dir: Path | None = None) -> None:
    """Render a fictional sample only; outputs go inside ignored .venv."""
    if venv_dir is None:
        venv_dir = VENV
    command = venv_command("rendercv", venv_dir)
    venv_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="smoke_", dir=venv_dir) as tmp:
        smoke_render_into(command, Path(tmp))
        output = venv_dir / "smoke"
        output.mkdir(exist_ok=True)
        for item in Path(tmp).iterdir():
            if item.suffix in (".pdf", ".png"):
                shutil.copy2(item, output / item.name)


def smoke_render_into(command: Path, output: Path) -> None:
    """Stage fresh artifacts so an old PDF cannot pass a new smoke check."""
    output.mkdir(parents=True, exist_ok=True)
    result = run(
        [
            str(command),
            "render",
            str(ROOT / "templates" / "rendercv.example.yaml"),
            "--quiet",
            "--pdf-path",
            str(output / "sample.pdf"),
            "--png-path",
            str(output / "preview.png"),
            "--typst-path",
            str(output / "sample.typ"),
            "--dont-generate-markdown",
            "--dont-generate-html",
        ]
    )
    if result.returncode != 0:
        raise BootstrapError(f"RenderCV smoke render failed:\n{result.stdout}\n{result.stderr}")
    if not (output / "sample.pdf").is_file():
        raise BootstrapError("RenderCV finished without creating the sample PDF")
    if not list(output.glob("*.png")):
        raise BootstrapError("RenderCV finished without creating a sample preview PNG")


def bootstrap(*, dev: bool = False, dry_run: bool = False) -> None:
    if sys.version_info[:2] < MIN_PYTHON:
        raise BootstrapError("Python >= 3.12 required. Install Python 3.12+ and rerun bootstrap")
    requirements = ROOT / ("requirements-dev.txt" if dev else "requirements.txt")
    pins, fingerprint = requirements_tree(requirements)
    python = venv_python()
    print(f"[resume-pilot] Python {sys.version.split()[0]} | {requirements.name}")
    if not python.exists():
        if VENV.exists():
            raise BootstrapError(
                ".venv exists but has no Python executable; repair/move it manually"
            )
        if dry_run:
            print("[dry-run] Would create .venv")
            return
        try:
            venv.EnvBuilder(with_pip=True).create(VENV)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise BootstrapError(
                f"Unable to create venv: {exc}. On some Linux distributions install python3-venv."
            ) from exc
    verify_venv(python)
    try:
        stamp: dict[str, Any] = json.loads(STAMP.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stamp = {}
    if not isinstance(stamp, dict):
        stamp = {}
    current = dependencies_ok(python, pins)
    cli_ready = rendercv_ok(python)
    if current and cli_ready and stamp.get("fingerprint") == fingerprint:
        print("[resume-pilot] Dependencies already correct. Skipping install.")
        return
    if dry_run:
        action = (
            "smoke-test existing packages" if current and cli_ready else "install needed packages"
        )
        print(f"[dry-run] Would {action} without unnecessary reinstall")
        return
    if current and cli_ready:
        print("[resume-pilot] All pinned packages already installed; skipping pip.")
    else:
        print("[resume-pilot] Installing/repairing required packages (pip keeps satisfied ones)...")
        result = run([str(python), "-m", "pip", "install", "-r", str(requirements)])
        if result.returncode != 0:
            raise BootstrapError(f"pip install failed:\n{result.stdout}\n{result.stderr}")
        if not dependencies_ok(python, pins):
            raise BootstrapError(
                "Installed packages are inconsistent: inspect `<venv-python> -m pip check`"
            )
        if not rendercv_ok(python):
            raise BootstrapError("RenderCV 2.8 executable unavailable or incorrect")
    smoke_render()
    STAMP.write_text(json.dumps({"fingerprint": fingerprint, "dev": dev}) + "\n", encoding="utf-8")
    print("[resume-pilot] Ready. Run `python scripts/cv.py doctor`.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", action="store_true", help="Install development and coverage tools")
    parser.add_argument("--dry-run", action="store_true", help="Report work without installing")
    args = parser.parse_args(argv)
    try:
        bootstrap(dev=args.dev, dry_run=args.dry_run)
    except BootstrapError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
