"""Focused entry for generating the native `str.isalnum()` table of the running Python."""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

from scripts.python_char_table._helpers.table import alnum_ranges, render_table, table_path


def generate_python_char_table() -> int:
    """Write the table of this Python's Unicode version next to the native text helpers."""

    path: Path = table_path()
    _ = path.write_text(render_table(alnum_ranges()), encoding="utf-8")
    print(f"wrote {path} (Unicode {unicodedata.unidata_version})", file=sys.stderr)
    return 0
