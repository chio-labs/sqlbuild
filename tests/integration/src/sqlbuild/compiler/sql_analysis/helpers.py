"""Read the wheel-site records a test process wrote."""

from __future__ import annotations

import json
from pathlib import Path

from sqlbuild.compiler.sql_analysis.constants import POLYGLOT_SITE_RECORD_PREFIX


def recorded_rows(root: Path) -> tuple[tuple[str, str, int], ...]:
    """Return every `(site, api, calls)` row the site recorder wrote below `root`."""

    rows: list[tuple[str, str, int]] = []
    for path in sorted(root.rglob(f"{POLYGLOT_SITE_RECORD_PREFIX}*.json")):
        for site, api, count in json.loads(path.read_text(encoding="utf-8"))["calls"]:
            rows.append((str(site), str(api), int(count)))
    return tuple(rows)
