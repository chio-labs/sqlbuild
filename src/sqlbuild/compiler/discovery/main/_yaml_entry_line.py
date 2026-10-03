"""Locate one named entry in an authored YAML declaration file."""

from __future__ import annotations

import re


def yaml_entry_line(*, contents: str, name: str) -> int | None:
    """Return the 1-based line of the outermost `- name: <name>` entry, if present."""

    pattern: re.Pattern[str] = re.compile(
        rf"^(?P<indent>\s*)-\s*name:\s*(?P<quote>['\"]?){re.escape(name)}(?P=quote)\s*(#.*)?$"
    )
    best: tuple[int, int] | None = None
    index: int
    line: str
    for index, line in enumerate(contents.splitlines(), start=1):
        match: re.Match[str] | None = pattern.match(line)
        if match is None:
            continue
        indent: int = len(match.group("indent"))
        if best is None or indent < best[0]:
            best = (indent, index)
    return None if best is None else best[1]
