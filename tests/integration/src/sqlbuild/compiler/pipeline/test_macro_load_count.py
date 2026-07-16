from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import (
    MacroLoadCountIntegrationTestCase,
)
from tests.integration.src.sqlbuild.compiler.pipeline.helpers import (
    run_compile_pipeline_for_project,
)

_PROJECT_TOML: str = 'name = "demo"\nadapter = "duckdb"\n\n[connection]\ndatabase = ":memory:"\n'

_COUNTING_MACRO_MODULE: str = (
    "from pathlib import Path\n"
    "\n"
    "_LOG_PATH = Path(__file__).resolve().parent.parent / 'macro_import_log.txt'\n"
    "with _LOG_PATH.open('a', encoding='utf-8') as handle:\n"
    "    handle.write('import\\n')\n"
    "\n"
    "\n"
    "def order_tag():\n"
    "    return \"'tagged'\"\n"
)


@pytest.mark.parametrize(
    "test_case",
    [
        MacroLoadCountIntegrationTestCase(
            description="user macro modules execute exactly once per compile pipeline run",
            project_files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "macros/counting.py": _COUNTING_MACRO_MODULE,
                "models/orders.sql": (
                    "MODEL (materialized table);\n\nSELECT 1 AS order_id, @order_tag() AS tag"
                ),
            },
            expected_macro_import_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_side_effect_macro_when_running_compile_pipeline_then_imports_macros_once(
    test_case: MacroLoadCountIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    run_compile_pipeline_for_project(
        project_dir=tmp_path,
        adapter=DuckDbAdapter(),
    )

    import_log: str = (tmp_path / "macro_import_log.txt").read_text(encoding="utf-8")
    assert import_log.count("import") == test_case.expected_macro_import_count
