"""Debug-only record of the model analysis work native hands back to Python."""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlbuild.compiler.analysis_session.constants import ANALYSIS_DEFERRAL_SITE
from sqlbuild.compiler.lineage.constants import ANALYSIS_DEFERRAL_RECORD_PREFIX
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR


def record_analysis_deferral(*, kind: str, count: int = 1) -> None:
    """Append `count` `{"kind", "site"}` lines when the analysis record directory is set."""

    directory: str | None = os.environ.get(ANALYSIS_RECORD_DIR_ENV_VAR)
    if not directory or count <= 0:
        return
    target: Path = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    record: str = json.dumps({"kind": kind, "site": ANALYSIS_DEFERRAL_SITE})
    with open(target / f"{ANALYSIS_DEFERRAL_RECORD_PREFIX}{os.getpid()}.jsonl", "a") as handle:
        _ = handle.write((record + "\n") * count)
