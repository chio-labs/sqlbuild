from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.scopes.models import DeclarationRecord
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import (
    MacroCompositionIntegrationTestCase,
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


@pytest.mark.parametrize(
    "test_case",
    [
        MacroCompositionIntegrationTestCase(
            description="private helper composition reaches scope and manifest dependency",
            project_files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "macros/shared.py": "def shared() -> str:\n    return 'order_id'\n",
                "macros/orders.py": (
                    "from macros.shared import shared\n\n"
                    "def _helper() -> str:\n    return shared()\n\n"
                    "def order_column() -> str:\n    return _helper()\n"
                ),
                "models/orders.sql": "MODEL (materialized table);\n\nSELECT @order_column()",
            },
            macro_name="order_column",
            expected_dependencies=("shared",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_composed_macro_when_compiling_then_scope_and_manifest_emit_dependency(
    test_case: MacroCompositionIntegrationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    result: CompilePipelineResult = run_compile_pipeline_for_project(
        project_dir=tmp_path,
        adapter=DuckDbAdapter(),
    )
    manifest: dict[str, object] = build_manifest_for_pipeline_result(
        result=result,
        project_name="demo",
        adapter_type="duckdb",
    )

    records: dict[str, DeclarationRecord] = {
        record.identity.name: record for record in result.project.scope_index.declarations
    }
    order_record: DeclarationRecord = records[test_case.macro_name]
    assert order_record.macro is not None
    assert (
        tuple(item.name for item in order_record.macro.dependencies)
        == test_case.expected_dependencies
    )
    macros: dict[str, object] = cast(dict[str, object], manifest["macros"])
    macro_node: dict[str, object] = cast(
        dict[str, object], macros[f"macro.demo.{test_case.macro_name}"]
    )
    assert macro_node["depends_on"] == {
        "macros": [f"macro.demo.{name}" for name in test_case.expected_dependencies]
    }
