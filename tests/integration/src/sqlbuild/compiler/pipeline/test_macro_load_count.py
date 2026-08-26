from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import (
    MacroLoadCountIntegrationTestCase,
)
from tests.integration.src.sqlbuild.compiler.pipeline.helpers import (
    build_manifest_for_pipeline_result,
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
            description="user macro modules execute once across compile and manifest generation",
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
def test_given_side_effect_macro_when_compiling_manifest_then_imports_macros_once(
    test_case: MacroLoadCountIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    result: CompilePipelineResult = run_compile_pipeline_for_project(
        project_dir=tmp_path,
        adapter=DuckDbAdapter(),
    )
    _ = build_manifest_for_pipeline_result(
        result=result,
        project_name="demo",
        adapter_type="duckdb",
    )

    import_log: str = (tmp_path / "macro_import_log.txt").read_text(encoding="utf-8")
    assert import_log.count("import") == test_case.expected_macro_import_count
