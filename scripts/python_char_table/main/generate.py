"""Focused entry for generating the native `str` character tables of the running Python."""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

from scripts.python_char_table._helpers.table import character_ranges, render_table, table_path
from scripts.python_char_table.constants import TABLE_METHODS


def generate_python_char_table() -> int:
    """Write this Python's Unicode version tables next to the native text helpers."""

    for method in TABLE_METHODS:
        path: Path = table_path(method=method)
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(
            render_table(method=method, ranges=character_ranges(method=method)), encoding="utf-8"
        )
        print(f"wrote {path} (Unicode {unicodedata.unidata_version})", file=sys.stderr)
    return 0
