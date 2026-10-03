"""Index the outermost `- name:` entries of authored YAML declaration files."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from functools import lru_cache

_ENTRY_PREFIX: re.Pattern[str] = re.compile(r"(?P<indent>\s*)-\s*name:")
_COMMENT_START: str = "#"
_QUOTES: tuple[str, ...] = ("", "'", '"')


@lru_cache(maxsize=16)
def yaml_entry_lines(contents: str) -> Mapping[str, int]:
    """Index every entry name once so per-resource lookups stay linear in file size."""

    best: dict[str, tuple[int, int]] = {}
    index: int
    line: str
    for index, line in enumerate(contents.splitlines(), start=1):
        prefix: re.Match[str] | None = _ENTRY_PREFIX.match(line)
        if prefix is None:
            continue
        indent: int = len(prefix.group("indent"))
        for name in _entry_names(line[prefix.end() :]):
            current: tuple[int, int] | None = best.get(name)
            if current is None or indent < current[0]:
                best[name] = (indent, index)
    return {name: line_number for name, (_, line_number) in best.items()}


def _entry_names(value: str) -> Iterator[str]:
    """Yield every name `\\s*(['"]?)<name>\\1\\s*(#.*)?$` accepts for one entry value."""

    closings: tuple[int, ...] = _closing_positions(value)
    for start in range(_leading_whitespace(text=value, start=0) + 1):
        for quote in _QUOTES:
            if not value.startswith(quote, start):
                continue
            body_start: int = start + len(quote)
            for closing in closings:
                end: int = closing - len(quote)
                if end >= body_start and value.startswith(quote, end):
                    yield value[body_start:end]


def _closing_positions(value: str) -> tuple[int, ...]:
    """Return positions after which only whitespace and an optional comment remain."""

    positions: list[int] = []
    tail: int = len(value)
    while tail >= 0:
        position: int = tail
        positions.append(position)
        while position > 0 and value[position - 1].isspace():
            position -= 1
            positions.append(position)
        tail = value.rfind(_COMMENT_START, 0, tail)
    return tuple(sorted(set(positions)))


def _leading_whitespace(*, text: str, start: int) -> int:
    position: int = start
    while position < len(text) and text[position].isspace():
        position += 1
    return position
