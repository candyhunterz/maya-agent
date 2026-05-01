"""Write a Maya .mod file that points at this repo, so Maya picks up the package.

Usage:
  python scripts/install_into_maya.py [--maya-version 2024]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _maya_modules_dir(maya_version: str) -> Path:
    if sys.platform == "win32":
        return Path(os.environ["USERPROFILE"]) / "Documents" / "maya" / maya_version / "modules"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Preferences" / "Autodesk" / "maya" / maya_version / "modules"
    else:
        return Path.home() / "maya" / maya_version / "modules"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--maya-version", default="2024")
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    src_path = repo_root / "src"
    if not src_path.exists():
        print(f"Expected src/ at {src_path}", file=sys.stderr)
        return 1

    modules_dir = _maya_modules_dir(args.maya_version)
    modules_dir.mkdir(parents=True, exist_ok=True)

    mod_path = modules_dir / "maya-agent.mod"
    mod_path.write_text(
        f"+ MAYAVERSION:{args.maya_version} maya-agent 0.1.0 {repo_root}\n"
        f"PYTHONPATH +:= src\n"
    )
    print(f"Wrote {mod_path}")
    print(f"Restart Maya {args.maya_version}; then run:")
    print(f"  import maya_agent.maya.maya_bootstrap as b; b.show_panel()")
    return 0


if __name__ == "__main__":
    sys.exit(main())
