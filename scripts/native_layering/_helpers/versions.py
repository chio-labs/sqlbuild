"""Check that every release version source names the same version."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from scripts.native_layering.constants import (
    CARGO_MANIFEST,
    PYPROJECT_MANIFEST,
    RELEASE_MANIFEST,
    RELEASE_MANIFEST_PACKAGE,
)


def get_native_version_errors(root: Path) -> tuple[str, ...]:
    """Return an error when the Cargo workspace, Python package and release versions differ."""
    with (root / CARGO_MANIFEST).open("rb") as handle:
        cargo: dict[str, Any] = tomllib.load(handle)
    with (root / PYPROJECT_MANIFEST).open("rb") as handle:
        pyproject: dict[str, Any] = tomllib.load(handle)
    release: dict[str, Any] = json.loads((root / RELEASE_MANIFEST).read_text(encoding="utf-8"))
    versions: dict[str, Any] = {
        f"{CARGO_MANIFEST} [workspace.package] version": cargo.get("workspace", {})
        .get("package", {})
        .get("version"),
        f"{PYPROJECT_MANIFEST} [project] version": pyproject.get("project", {}).get("version"),
        f"{RELEASE_MANIFEST} version": release.get(RELEASE_MANIFEST_PACKAGE),
    }
    if len(set(versions.values())) == 1:
        return ()
    listed: str = ", ".join(f"{source} is {version}" for source, version in versions.items())
    return (f"Release versions differ: {listed}.",)
