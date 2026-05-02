"""Doctor for the maya-agent studio environment.

Runs entirely on the local machine — no network calls except a 2-second probe
to localhost:11434 (Ollama). Stdlib only, so it works on a stock Python install
before anything has been pip-installed.

Usage:
    python scripts/check-studio-env.py

Exits 0 if all required deps are present, 1 otherwise.
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

OLLAMA_URL = os.environ.get("MAYA_AGENT_OLLAMA_URL", "http://localhost:11434")
TARGET_MODELS = ("gemma4:31b", "gemma3:27b")
MIN_PYTHON = (3, 10)
MIN_PYDANTIC = (2, 6)


class Result(NamedTuple):
    label: str
    ok: bool
    detail: str
    fix: str = ""


def check_host_python() -> Result:
    v = sys.version_info
    s = f"Python {v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= MIN_PYTHON:
        return Result("Host Python", True, s)
    return Result(
        "Host Python", False, s,
        f"need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ — install a newer Python on the studio host",
    )


def check_module(name: str, min_version: tuple[int, ...] | None = None) -> Result:
    spec = importlib.util.find_spec(name)
    if spec is None:
        return Result(
            f"  {name}", False, "NOT INSTALLED",
            f"pip install --no-index --find-links=./wheels {name}",
        )
    try:
        mod = __import__(name)
        ver = getattr(mod, "__version__", None) or getattr(mod, "VERSION", "unknown")
        if isinstance(ver, tuple):
            ver = ".".join(str(p) for p in ver)
        ver_str = str(ver)
    except Exception as e:  # pragma: no cover - defensive
        return Result(f"  {name}", False, f"import failed: {e}")
    if min_version:
        try:
            parts = tuple(int(p) for p in ver_str.split(".")[: len(min_version)])
            if parts < min_version:
                need = ".".join(str(p) for p in min_version)
                return Result(
                    f"  {name}", False, f"{ver_str} (need {need}+)",
                    f"pip install --no-index --find-links=./wheels '{name}>={need}'",
                )
        except ValueError:
            pass  # non-numeric version, accept
    return Result(f"  {name}", True, ver_str)


def find_maya_installs() -> list[Path]:
    """Return mayapy paths for any Maya install we can find."""
    found: list[Path] = []
    system = platform.system()
    versions = ("2026", "2025", "2024")
    if system == "Windows":
        for v in versions:
            p = Path(rf"C:\Program Files\Autodesk\Maya{v}\bin\mayapy.exe")
            if p.exists():
                found.append(p)
    elif system == "Linux":
        for v in versions:
            p = Path(f"/usr/autodesk/maya{v}/bin/mayapy")
            if p.exists():
                found.append(p)
    elif system == "Darwin":
        for v in versions:
            p = Path(f"/Applications/Autodesk/maya{v}/Maya.app/Contents/bin/mayapy")
            if p.exists():
                found.append(p)
    # Also try whatever's on PATH
    on_path = shutil.which("mayapy")
    if on_path and Path(on_path) not in found:
        found.append(Path(on_path))
    return found


def check_mayapy(mayapy: Path) -> list[Result]:
    """Probe a mayapy binary for Python version and Qt binding."""
    label_root = mayapy.parent.parent.name  # Maya2024 / Maya2025 / etc
    results: list[Result] = []

    # Python version
    try:
        out = subprocess.run(
            [str(mayapy), "--version"],
            capture_output=True, text=True, timeout=15,
        )
        py_str = (out.stdout + out.stderr).strip()
        results.append(Result(f"  {label_root} mayapy", True, py_str or str(mayapy)))
    except (subprocess.TimeoutExpired, OSError) as e:
        results.append(Result(f"  {label_root} mayapy", False, f"failed to run: {e}"))
        return results

    # PySide6 first (Maya 2025+), fall back to PySide2 (Maya 2024)
    for binding in ("PySide6", "PySide2"):
        try:
            out = subprocess.run(
                [str(mayapy), "-c", f"import {binding}; print({binding}.__version__)"],
                capture_output=True, text=True, timeout=20,
            )
            if out.returncode == 0:
                results.append(Result(f"    {binding}", True, out.stdout.strip()))
                return results
        except (subprocess.TimeoutExpired, OSError):
            continue

    results.append(Result(
        "    PySide6/PySide2", False, "neither importable in mayapy",
        "Maya 2024 ships PySide2 (panel needs port or PySide6 install); Maya 2025+ bundles PySide6",
    ))
    return results


def check_ollama_binary() -> Result:
    path = shutil.which("ollama")
    if not path:
        return Result(
            "Ollama binary", False, "not on PATH",
            "install ollama from the offline installer (~150MB)",
        )
    try:
        out = subprocess.run(
            ["ollama", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        return Result("Ollama binary", True, out.stdout.strip() or path)
    except (subprocess.TimeoutExpired, OSError) as e:
        return Result("Ollama binary", False, f"failed to run: {e}")


def check_ollama_server() -> tuple[Result, list[str]]:
    """Probe the Ollama HTTP server. Returns (result, list_of_pulled_models)."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        return Result(
            "Ollama server", False, f"unreachable at {OLLAMA_URL} ({e.reason})",
            "start it: `ollama serve` (or as a service)",
        ), []
    except (TimeoutError, json.JSONDecodeError) as e:
        return Result("Ollama server", False, f"bad response from {OLLAMA_URL}: {e}"), []
    models = [m.get("name", "") for m in data.get("models", [])]
    return Result("Ollama server", True, f"reachable at {OLLAMA_URL}"), models


def check_models(pulled: list[str]) -> list[Result]:
    results: list[Result] = []
    for target in TARGET_MODELS:
        if any(m == target or m.startswith(target + ":") for m in pulled):
            results.append(Result(f"  model {target}", True, "pulled"))
        else:
            results.append(Result(
                f"  model {target}", False, "not pulled",
                f"on a connected box: `ollama pull {target}`, then copy "
                "~/.ollama/models/ to the studio host",
            ))
    return results


def render(results: list[Result]) -> int:
    ok_mark = "[OK]"
    bad_mark = "[!!]"
    width = max((len(r.label) for r in results), default=20) + 2
    n_ok = sum(1 for r in results if r.ok)
    n_bad = len(results) - n_ok
    print()
    print("=== Maya Agent Studio Environment Check ===")
    print()
    for r in results:
        mark = ok_mark if r.ok else bad_mark
        print(f"  {mark} {r.label.ljust(width)} {r.detail}")
        if not r.ok and r.fix:
            print(f"           fix: {r.fix}")
    print()
    print(f"Summary: {n_ok} OK, {n_bad} missing/broken")
    return 0 if n_bad == 0 else 1


def main() -> int:
    results: list[Result] = []

    results.append(check_host_python())
    results.append(check_module("httpx"))
    results.append(check_module("pydantic", min_version=MIN_PYDANTIC))

    maya_paths = find_maya_installs()
    if not maya_paths:
        results.append(Result(
            "Maya install", False, "no mayapy found in standard locations or on PATH",
            "install Maya 2024+ (only needed on the panel host, not the sidecar host)",
        ))
    else:
        for mp in maya_paths:
            results.extend(check_mayapy(mp))

    ollama_bin = check_ollama_binary()
    results.append(ollama_bin)
    if ollama_bin.ok:
        server_result, pulled = check_ollama_server()
        results.append(server_result)
        if server_result.ok:
            results.extend(check_models(pulled))

    return render(results)


if __name__ == "__main__":
    sys.exit(main())
