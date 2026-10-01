"""Parse the TOML snippet shown by a diagnostic help text."""

from __future__ import annotations

import re
import tomllib

from scripts.setting_help.constants import SNIPPET_PATTERN


def parse_setting_snippet(help_text: str) -> tuple[str, str, object] | None:
    """Return `(section, key, value)` from the first `[section]` / `key = value` snippet."""

    match: re.Match[str] | None = SNIPPET_PATTERN.search(help_text)
    if match is None:
        return None
    section, key, value = match.groups()
    return section, key, tomllib.loads(f"value = {value}")["value"]
