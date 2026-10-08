"""The debug site recorder counts wheel calls by product site only when its directory is set."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR
from tests.integration.src.sqlbuild.compiler.sql_analysis._test_types import SiteRecorderTestCase
from tests.integration.src.sqlbuild.compiler.sql_analysis.helpers import recorded_rows

_PROCESS: str = (
    "from sqlbuild.compiler.references.main.extract_relation_names import "
    "extract_relation_names\n"
    "from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql\n"
    "for _ in range(2):\n"
    "    assert extract_relation_names(sql='SELECT 1 FROM main.orders', dialect='duckdb')\n"
    "module = import_polyglot_sql()\n"
    "print(type(module.parse_one).__name__, isinstance(module.PolyglotError, type))\n"
)
_SITE: str = "compiler/references/_helpers/relation_names.py:extract_relation_names_impl"


@pytest.mark.parametrize(
    "test_case",
    [
        SiteRecorderTestCase(
            description="recording",
            record_dir="records",
            expected_rows=((_SITE, "parse", 2),),
            expected_entry_point="_RecordedEntryPoint",
        ),
        SiteRecorderTestCase(
            description="disabled",
            record_dir="",
            expected_rows=(),
            expected_entry_point="_GuardedEntryPoint",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_record_dir_when_process_calls_the_wheel_then_sites_are_counted_at_exit(
    test_case: SiteRecorderTestCase, tmp_path: Path
) -> None:
    completed: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, "-c", _PROCESS],
        cwd=tmp_path,
        env={**os.environ, ANALYSIS_RECORD_DIR_ENV_VAR: test_case.record_dir},
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    assert recorded_rows(tmp_path) == test_case.expected_rows
    assert completed.stdout.split() == [test_case.expected_entry_point, "True"]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
