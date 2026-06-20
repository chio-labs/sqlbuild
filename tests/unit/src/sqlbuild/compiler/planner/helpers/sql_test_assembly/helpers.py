"""Test helpers for sql_test_assembly tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlbuild.compiler.compile.constants import (
    DBT_REF_TEST_CTE_PREFIX,
    EXPECTED_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.helpers.macros import expand_sql_macros
from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompileModelConfig,
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.compile.models.sql_tests import (
    CompiledModelSqlTestPayload,
    CompiledSqlTest,
    CompileSqlTestCte,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import (
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.sql_test_assembly._test_types import (
    PlanTestChainTestCase,
)

_STUB_TEST_FILE: DiscoveredSqlTestFile = DiscoveredSqlTestFile(
    file_path=Path("tests/unit/test_chain.sql"),
    relative_path=Path("tests/unit/test_chain.sql"),
    contents="",
    blocks=(),
)

_STUB_TEST_BLOCK: DiscoveredSqlTestBlock = DiscoveredSqlTestBlock(
    test_index=0,
    header_values={},
    sql_body="",
)

_MACRO_CONTEXT: MacroContext = MacroContext(
    adapter_name="duckdb",
    sql_analysis_enabled=True,
    target_name=None,
    vars={},
)


def build_test_and_project(
    test_case: PlanTestChainTestCase,
) -> tuple[CompiledSqlTest, CompiledProject]:
    """Build a CompiledSqlTest and CompiledProject from a test case."""

    authored_ctes: list[CompileSqlTestCte] = []
    name: str
    body: str
    for name, body in test_case.mock_ref_ctes.items():
        authored_ctes.append(
            CompileSqlTestCte(
                name=f"{REF_TEST_CTE_PREFIX}{name}",
                sql_body=body,
            )
        )
    for name, body in test_case.mock_source_ctes.items():
        authored_ctes.append(
            CompileSqlTestCte(
                name=f"{SOURCE_TEST_CTE_PREFIX}{name}",
                sql_body=body,
            )
        )
    for name, body in test_case.mock_seed_ctes.items():
        authored_ctes.append(
            CompileSqlTestCte(
                name=f"{SEED_TEST_CTE_PREFIX}{name}",
                sql_body=body,
            )
        )
    for name, body in test_case.mock_dbt_ref_ctes.items():
        authored_ctes.append(
            CompileSqlTestCte(
                name=f"{DBT_REF_TEST_CTE_PREFIX}{name}",
                sql_body=body,
            )
        )
    for name, body in test_case.helper_ctes.items():
        authored_ctes.append(CompileSqlTestCte(name=name, sql_body=body))

    sql_body: str = test_case.sql_body
    if not sql_body:
        sql_body = _build_test_sql_body(
            test_case.mock_ref_ctes,
            test_case.mock_source_ctes,
            test_case.mock_seed_ctes,
            test_case.mock_dbt_ref_ctes,
            test_case.helper_ctes,
            test_case.expected_cte_bodies,
        )

    loaded_macros: dict[str, LoadedMacro] = _build_loaded_macros(test_case.loaded_macro_outputs)
    compiled_test: CompiledSqlTest = CompiledSqlTest(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_TEST,
            name="test_chain",
        ),
        scope_deps=tuple(
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=n)
            for n in test_case.expected_model_names
        ),
        name="test_chain",
        test_file=_STUB_TEST_FILE,
        test_block=_STUB_TEST_BLOCK,
        sql_body=sql_body,
        payload=CompiledModelSqlTestPayload(
            authored_ctes=tuple(authored_ctes),
            macro_mocks=test_case.macro_mocks,
            model_query_overrides=_build_model_query_overrides(
                test_case=test_case,
                loaded_macros=loaded_macros,
            ),
            mock_model_names=tuple(test_case.mock_ref_ctes.keys()),
            mock_source_names=tuple(test_case.mock_source_ctes.keys()),
            mock_seed_names=tuple(test_case.mock_seed_ctes.keys()),
            mock_dbt_ref_names=tuple(test_case.mock_dbt_ref_ctes.keys()),
            expected_model_names=test_case.expected_model_names,
        ),
    )

    models: list[CompiledModel] = []
    model_name: str
    query_sql: str
    for model_name, query_sql in test_case.model_queries.items():
        models.append(
            CompiledModel(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.MODEL,
                    name=model_name,
                ),
                deps=(),
                name=model_name,
                relative_path=Path(f"models/{model_name}.sql"),
                query_sql=query_sql,
                config=CompileModelConfig(),
                destination=CompiledRelationLocation(
                    database=None,
                    schema="staging",
                    name=model_name,
                    qualified_name=f"staging.{model_name}",
                ),
            )
        )

    functions: list[CompiledFunction] = []
    function_name: str
    qualified_name: str
    for function_name, qualified_name in test_case.function_locations.items():
        functions.append(
            CompiledFunction(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.UDF,
                    name=function_name,
                ),
                deps=(),
                name=function_name,
                relative_path=Path(f"functions/sql/{function_name}.sql"),
                arguments=(),
                returns="BOOLEAN",
                body_sql="SELECT TRUE",
                destination=CompiledRelationLocation(
                    database=None,
                    schema="main",
                    name=function_name,
                    qualified_name=qualified_name,
                ),
                fingerprint_destination=CompiledRelationLocation(
                    database=None,
                    schema="main",
                    name=function_name,
                    qualified_name=qualified_name,
                ),
            )
        )

    project: CompiledProject = CompiledProject(
        run_id="test_run",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        models=tuple(models),
        functions=tuple(functions),
    )

    return compiled_test, project


def _build_model_query_overrides(
    *,
    test_case: PlanTestChainTestCase,
    loaded_macros: dict[str, LoadedMacro],
) -> dict[str, str]:
    """Build model query overrides for planner tests with macro mocks."""

    overrides: dict[str, str] = dict(test_case.model_query_overrides)
    if not test_case.macro_mocks:
        return overrides
    model_name: str
    query_sql: str
    for model_name, query_sql in test_case.model_macro_source_queries.items():
        overrides[model_name] = expand_sql_macros(
            sql=query_sql,
            file_path=Path(f"models/{model_name}.sql"),
            loaded_macros=loaded_macros,
            macro_overrides=test_case.macro_mocks,
            macro_context=_MACRO_CONTEXT,
        )
    return overrides


def _build_loaded_macros(macro_outputs: dict[str, str]) -> dict[str, LoadedMacro]:
    """Build loaded macro stubs for planner tests."""

    loaded_macros: dict[str, LoadedMacro] = {}
    name: str
    output: str
    for name, output in macro_outputs.items():
        loaded_macros[name] = LoadedMacro(
            name=name,
            file_path=Path("macros/test_macros.py"),
            relative_path=Path("macros/test_macros.py"),
            raw_source="",
            function=_macro_function(output),
        )
    return loaded_macros


def _macro_function(output: str) -> Callable[..., object]:
    """Return a callable macro stub."""

    def _inner(*_args: object, **_kwargs: object) -> str:
        return output

    return _inner


def _build_test_sql_body(
    mock_refs: dict[str, str],
    mock_sources: dict[str, str],
    mock_seeds: dict[str, str],
    mock_dbt_refs: dict[str, str],
    helpers: dict[str, str],
    expected_bodies: dict[str, str],
) -> str:
    """Build a synthetic test sql_body containing expected CTEs."""

    parts: list[str] = []
    name: str
    body: str
    for name, body in mock_refs.items():
        parts.append(f"{REF_TEST_CTE_PREFIX}{name} AS ({body})")
    for name, body in mock_sources.items():
        parts.append(f"{SOURCE_TEST_CTE_PREFIX}{name} AS ({body})")
    for name, body in mock_seeds.items():
        parts.append(f"{SEED_TEST_CTE_PREFIX}{name} AS ({body})")
    for name, body in mock_dbt_refs.items():
        parts.append(f"{DBT_REF_TEST_CTE_PREFIX}{name} AS ({body})")
    for name, body in helpers.items():
        parts.append(f"{name} AS ({body})")
    for name, body in expected_bodies.items():
        parts.append(f"{EXPECTED_TEST_CTE_PREFIX}{name} AS ({body})")
    if not parts:
        return "SELECT 1"
    return "WITH " + ", ".join(parts) + " SELECT 1"
