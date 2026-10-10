"""Debug-only record of lineage models the native engine hands back to Python."""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlbuild.compiler.lineage.constants import (
    ANALYSIS_DEFERRAL_RECORD_PREFIX,
    NATIVE_LINEAGE_DEFERRAL_SITE,
)
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR


def record_lineage_deferral(*, kind: str, site: str = NATIVE_LINEAGE_DEFERRAL_SITE) -> None:
    """Append one `{"kind", "site"}` line when the analysis record directory is set."""

    directory: str | None = os.environ.get(ANALYSIS_RECORD_DIR_ENV_VAR)
    if not directory:
        return
    target: Path = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    record: str = json.dumps({"kind": kind, "site": site})
    with open(target / f"{ANALYSIS_DEFERRAL_RECORD_PREFIX}{os.getpid()}.jsonl", "a") as handle:
        _ = handle.write(record + "\n")
