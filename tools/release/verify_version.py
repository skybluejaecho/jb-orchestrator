"""Validate that a stable Git tag matches every shipped component version."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

STABLE_TAG = re.compile(r"^v(?P<version>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))$")


def component_versions(root: Path) -> dict[str, str]:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    jarvis_package = json.loads(
        (root / "apps" / "jarvis" / "package.json").read_text(encoding="utf-8")
    )
    return {
        "runtime": str(pyproject["project"]["version"]),
        "jarvis": str(jarvis_package["version"]),
    }


def verify_version(tag: str, root: Path) -> str:
    match = STABLE_TAG.fullmatch(tag)
    if match is None:
        raise ValueError(f"release tag must be stable SemVer in vX.Y.Z form: {tag}")

    expected = match.group("version")
    mismatches = {
        component: version
        for component, version in component_versions(root).items()
        if version != expected
    }
    if mismatches:
        rendered = ", ".join(f"{key}={value}" for key, value in sorted(mismatches.items()))
        raise ValueError(f"release tag {tag} does not match component versions: {rendered}")
    return expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag", help="stable release tag in vX.Y.Z form")
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[2])
    arguments = parser.parse_args()
    try:
        version = verify_version(arguments.tag, arguments.root.resolve())
    except (KeyError, OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        print(f"release version validation failed: {error}", file=sys.stderr)
        return 1
    print(f"release version validated: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
