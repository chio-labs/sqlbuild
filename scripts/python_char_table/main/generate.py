"""Focused entry for regenerating the native `str.isalnum()` table with the CI Python."""

from __future__ import annotations

import sys
import unicodedata

from scripts.python_char_table._helpers.table import alnum_ranges, render_table
from scripts.python_char_table.constants import TABLE_PATH


def generate_python_char_table() -> int:
    """Write the table next to the native text helpers and report its Unicode version."""

    _ = TABLE_PATH.write_text(render_table(alnum_ranges()), encoding="utf-8")
    print(f"wrote {TABLE_PATH} (Unicode {unicodedata.unidata_version})", file=sys.stderr)
    return 0
