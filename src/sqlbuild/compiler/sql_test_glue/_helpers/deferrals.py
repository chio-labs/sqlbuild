"""Debug-only record of SQL tests the native assembly hands back to Python."""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlbuild.compiler.lineage.constants import ANALYSIS_DEFERRAL_RECORD_PREFIX
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR
from sqlbuild.compiler.sql_test_glue.constants import SQL_TEST_ASSEMBLY_DEFERRAL_SITE


def record_sql_test_assembly_deferral(*, kind: str) -> None:
    """Append one `{"kind", "site"}` line when the analysis record directory is set."""

    directory: str | None = os.environ.get(ANALYSIS_RECORD_DIR_ENV_VAR)
    if not directory:
        return
    target: Path = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    record: str = json.dumps({"kind": kind, "site": SQL_TEST_ASSEMBLY_DEFERRAL_SITE})
    with open(target / f"{ANALYSIS_DEFERRAL_RECORD_PREFIX}{os.getpid()}.jsonl", "a") as handle:
        _ = handle.write(record + "\n")
