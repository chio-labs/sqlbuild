"""Splice macro outputs in Python for text the native splice cannot read."""

from __future__ import annotations


def splice_text(
    *, sql: str, bounds: list[tuple[int, int]], outputs: list[str]
) -> tuple[str, list[tuple[int, int, int, int]]]:
    """Replace each `(start, end)` span with its output, as `splice_macro_calls` does."""

    parts: list[str] = []
    spans: list[tuple[int, int, int, int]] = []
    cursor: int = 0
    length: int = 0
    for (start, end), output in zip(bounds, outputs, strict=True):
        parts.append(sql[cursor:start])
        length += start - cursor
        parts.append(output)
        spans.append((start, end, length, length + len(output)))
        length += len(output)
        cursor = end
    parts.append(sql[cursor:])
    return "".join(parts), spans
