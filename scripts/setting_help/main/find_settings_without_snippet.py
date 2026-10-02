"""Find authored diagnostic text that names a setting without its exact TOML snippet."""

from __future__ import annotations

from pathlib import Path

from scripts.setting_help._helpers.scan import python_findings, rust_findings


def find_settings_without_snippet(repository_root: Path) -> list[str]:
    """Return `path:line: text` for Python and Rust strings that name a setting loosely."""

    return [*python_findings(repository_root), *rust_findings(repository_root)]
