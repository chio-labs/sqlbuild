from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.models.sql_tests import (
    CompiledDirectLogicSqlTestPayload,
    CompiledSqlTest,
    CompileSqlTestCte,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, SqlTestMode
from sqlbuild.compiler.discovery.models import DiscoveredSqlTestBlock, DiscoveredSqlTestFile
from sqlbuild.compiler.planner.helpers.sql_tests.assembly import plan_test
from sqlbuild.compiler.planner.models import (
    ChainStep,
    PlanWarning,
    SqlTestPlanEntry,
)
from sqlbuild.compiler.planner.types import WarningSeverity
from tests.unit.src.sqlbuild.compiler.planner.helpers.sql_test_assembly._test_types import (
    PlanMacroTestCase,
    PlanTestChainTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.sql_test_assembly.helpers import (
    build_test_and_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PlanTestChainTestCase(
            description="single model with mock dbt ref replaces dbt ref in sql",
            model_queries={
                "orders": 'SELECT order_id, amount FROM __dbt_ref("stg_orders")',
            },
            mock_ref_ctes={},
            mock_source_ctes={},
            mock_dbt_ref_ctes={
                "stg_orders": "SELECT 1 AS order_id, 100 AS amount",
            },
            helper_ctes={},
            expected_model_names=("orders",),
            expected_chain_length=1,
            expected_sql_fragments={
                "orders": "SELECT 1 AS order_id, 100 AS amount",
            },
            expected_cte_bodies={
                "orders": "SELECT 1 AS order_id, 100 AS amount",
            },
        ),
        PlanTestChainTestCase(
            description="single model with package-qualified mock dbt ref replaces dbt ref in sql",
            model_queries={
                "payments": 'SELECT payment_id FROM __dbt_ref("stripe", "payments")',
            },
            mock_ref_ctes={},
            mock_source_ctes={},
            mock_dbt_ref_ctes={
                "stripe__payments": "SELECT 1 AS payment_id",
            },
            helper_ctes={},
            expected_model_names=("payments",),
            expected_chain_length=1,
            expected_sql_fragments={
                "payments": "SELECT 1 AS payment_id",
            },
            expected_cte_bodies={
                "payments": "SELECT 1 AS payment_id",
            },
        ),
        PlanTestChainTestCase(
            description="single model with unmocked dbt ref reports missing mock error",
            model_queries={
                "payments": 'SELECT payment_id FROM __dbt_ref("stripe", "payments")',
            },
            mock_ref_ctes={},
            mock_source_ctes={},
            helper_ctes={},
            expected_model_names=("payments",),
            expected_chain_length=1,
            expected_warning_count=1,
            expected_warning_severity=WarningSeverity.ERROR,
            expected_error_fragment="__dbt_ref__stripe__payments which has no mock",
            expected_cte_bodies={
                "payments": 'SELECT payment_id FROM __dbt_ref("stripe", "payments")',
            },
        ),
        PlanTestChainTestCase(
            description="sql test macro mocks override model macro expansion before refs resolve",
            model_queries={
                "orders": "SELECT 1 AS id, 'real' AS country FROM __source(\"raw\")",
            },
            model_macro_source_queries={
                "orders": 'SELECT 1 AS id, @country() AS country FROM __source("raw")',
            },
            loaded_macro_outputs={"country": "'real'"},
            macro_mocks={"country": "'mocked'"},
            mock_ref_ctes={},
            mock_source_ctes={"raw": "SELECT 1 AS id"},
            helper_ctes={},
            expected_model_names=("orders",),
            expected_chain_length=1,
            expected_sql_fragments={"orders": "'mocked' AS country"},
            expected_cte_bodies={"orders": "SELECT 1 AS id, 'mocked' AS country"},
        ),
        PlanTestChainTestCase(
            description="unmocked macros keep real project macro expansion in sql tests",
            model_queries={
                "orders": "SELECT 1 AS id, 'real' AS country FROM __source(\"raw\")",
            },
            model_macro_source_queries={
                "orders": 'SELECT 1 AS id, @country() AS country FROM __source("raw")',
            },
            loaded_macro_outputs={"country": "'real'"},
            mock_ref_ctes={},
            mock_source_ctes={"raw": "SELECT 1 AS id"},
            helper_ctes={},
            expected_model_names=("orders",),
            expected_chain_length=1,
            expected_sql_fragments={"orders": "'real' AS country"},
            expected_cte_bodies={"orders": "SELECT 1 AS id, 'real' AS country"},
        ),
        PlanTestChainTestCase(
            description="single model with mock ref replaces ref in sql",
            model_queries={
                "orders": 'SELECT id, amount FROM __ref("raw_orders")',
            },
            mock_ref_ctes={
                "raw_orders": "SELECT 1 AS id, 100 AS amount",
            },
            mock_source_ctes={},
            helper_ctes={},
            expected_model_names=("orders",),
            expected_chain_length=1,
            expected_sql_fragments={
                "orders": "SELECT 1 AS id, 100 AS amount",
            },
            expected_cte_bodies={
                "orders": "SELECT 1 AS id, 100 AS amount",
            },
        ),
        PlanTestChainTestCase(
            description="single model with mock source replaces source in sql",
            model_queries={
                "stg_orders": 'SELECT id FROM __source("raw_orders")',
            },
            mock_ref_ctes={},
            mock_source_ctes={
                "raw_orders": "SELECT 1 AS id",
            },
            helper_ctes={},
            expected_model_names=("stg_orders",),
            expected_chain_length=1,
            expected_sql_fragments={
                "stg_orders": "SELECT 1 AS id",
            },
            expected_cte_bodies={
                "stg_orders": "SELECT 1 AS id",
            },
        ),
        PlanTestChainTestCase(
            description="single model with mock seed replaces seed in sql",
            model_queries={
                "orders": 'SELECT code FROM __seed("country_codes")',
            },
            mock_ref_ctes={},
            mock_source_ctes={},
            mock_seed_ctes={
                "country_codes": "SELECT 'US' AS code",
            },
            helper_ctes={},
            expected_model_names=("orders",),
            expected_chain_length=1,
            expected_sql_fragments={
                "orders": "SELECT 'US' AS code",
            },
            expected_cte_bodies={
                "orders": "SELECT 'US' AS code",
            },
        ),
        PlanTestChainTestCase(
            description="single model resolves udf references in sql tests",
            model_queries={
                "orders": 'SELECT __udf("is_ready")(status) AS ready FROM __source("raw")',
            },
            mock_ref_ctes={},
            mock_source_ctes={
                "raw": "SELECT 'completed' AS status",
            },
            helper_ctes={},
            expected_model_names=("orders",),
            expected_chain_length=1,
            function_locations={"is_ready": "main.is_ready"},
            expected_sql_fragments={
                "orders": "main.is_ready(status) AS ready",
            },
            expected_cte_bodies={
                "orders": "SELECT TRUE AS ready",
            },
        ),
        PlanTestChainTestCase(
            description="two model chain resolves in dependency order",
            model_queries={
                "stg_orders": 'SELECT id FROM __source("raw")',
                "fact_orders": ('SELECT id, 1 AS flag FROM __ref("stg_orders")'),
            },
            mock_ref_ctes={},
            mock_source_ctes={
                "raw": "SELECT 1 AS id",
            },
            helper_ctes={},
            expected_model_names=("stg_orders", "fact_orders"),
            expected_chain_length=2,
            expected_sql_fragments={
                "fact_orders": "SELECT 1 AS id",
            },
            expected_cte_bodies={
                "stg_orders": "SELECT 1 AS id",
                "fact_orders": "SELECT 1 AS id, 1 AS flag",
            },
        ),
        PlanTestChainTestCase(
            description="model query overrides drive dependency order",
            model_queries={
                "stg_orders": 'SELECT id FROM __source("raw")',
                "fact_orders": "SELECT id, 1 AS flag FROM staging.stg_orders",
            },
            model_query_overrides={
                "fact_orders": 'SELECT id, 1 AS flag FROM __ref("stg_orders")',
            },
            mock_ref_ctes={},
            mock_source_ctes={
                "raw": "SELECT 1 AS id",
            },
            helper_ctes={},
            expected_model_names=("fact_orders", "stg_orders"),
            expected_chain_length=2,
            expected_sql_fragments={
                "fact_orders": "SELECT 1 AS id",
            },
            expected_cte_bodies={
                "stg_orders": "SELECT 1 AS id",
                "fact_orders": "SELECT 1 AS id, 1 AS flag",
            },
        ),
        PlanTestChainTestCase(
            description="three model chain A to B to C",
            model_queries={
                "A": 'SELECT id FROM __source("raw")',
                "B": 'SELECT id, id * 2 AS doubled FROM __ref("A")',
                "C": ('SELECT id, doubled + 1 AS final FROM __ref("B")'),
            },
            mock_ref_ctes={},
            mock_source_ctes={
                "raw": "SELECT 1 AS id",
            },
            helper_ctes={},
            expected_model_names=("A", "B", "C"),
            expected_chain_length=3,
            expected_sql_fragments={
                "C": "doubled + 1 AS final",
            },
            expected_cte_bodies={
                "A": "SELECT 1 AS id",
                "B": "SELECT 1 AS id",
                "C": "SELECT 1 AS id",
            },
        ),
        PlanTestChainTestCase(
            description="helper ctes included in mock subquery",
            model_queries={
                "orders": 'SELECT id, amount FROM __ref("raw")',
            },
            mock_ref_ctes={
                "raw": "SELECT id, amount FROM gen_data",
            },
            mock_source_ctes={},
            helper_ctes={
                "gen_data": "SELECT 1 AS id, 100 AS amount",
            },
            expected_model_names=("orders",),
            expected_chain_length=1,
            expected_sql_fragments={
                "orders": "gen_data",
            },
            expected_cte_bodies={
                "orders": "SELECT 1 AS id, 100 AS amount",
            },
        ),
        PlanTestChainTestCase(
            description=("unreachable mock ref produces warning"),
            model_queries={
                "B": 'SELECT id FROM __ref("A")',
                "C": 'SELECT id FROM __ref("B")',
            },
            mock_ref_ctes={
                "A": "SELECT 1 AS id",
                "B": "SELECT 1 AS id",
            },
            mock_source_ctes={},
            helper_ctes={},
            expected_model_names=("C",),
            expected_chain_length=1,
            expected_sql_fragments={
                "C": "SELECT 1 AS id",
            },
            expected_warning_count=1,
            expected_warning_severity=WarningSeverity.WARNING,
            expected_cte_bodies={
                "C": "SELECT 1 AS id",
            },
        ),
        PlanTestChainTestCase(
            description="missing expected model produces error warning",
            model_queries={},
            mock_ref_ctes={
                "raw": "SELECT 1 AS id",
            },
            mock_source_ctes={},
            helper_ctes={},
            expected_model_names=("nonexistent",),
            expected_chain_length=0,
            expected_warning_count=2,
            expected_warning_severity=None,
            expected_cte_bodies={
                "nonexistent": "SELECT 1",
            },
        ),
        PlanTestChainTestCase(
            description="diamond dependency A to B and C both to D",
            model_queries={
                "B": 'SELECT id FROM __source("raw")',
                "C": 'SELECT id FROM __source("raw")',
                "D": ('SELECT b.id FROM __ref("B") b JOIN __ref("C") c ON b.id = c.id'),
            },
            mock_ref_ctes={},
            mock_source_ctes={
                "raw": "SELECT 1 AS id",
            },
            helper_ctes={},
            expected_model_names=("B", "C", "D"),
            expected_chain_length=3,
            expected_sql_fragments={
                "D": "SELECT 1 AS id",
            },
            expected_cte_bodies={
                "B": "SELECT 1 AS id",
                "C": "SELECT 1 AS id",
                "D": "SELECT 1 AS id",
            },
        ),
        PlanTestChainTestCase(
            description=("unresolved ref produces error warning"),
            model_queries={
                "orders": ('SELECT id FROM __ref("missing_model")'),
            },
            mock_ref_ctes={},
            mock_source_ctes={},
            helper_ctes={},
            expected_model_names=("orders",),
            expected_chain_length=1,
            expected_warning_count=1,
            expected_warning_severity=WarningSeverity.ERROR,
            expected_cte_bodies={
                "orders": "SELECT 1",
            },
        ),
        PlanTestChainTestCase(
            description=("unresolved source produces error warning"),
            model_queries={
                "orders": ('SELECT id FROM __source("missing_source")'),
            },
            mock_ref_ctes={},
            mock_source_ctes={},
            helper_ctes={},
            expected_model_names=("orders",),
            expected_chain_length=1,
            expected_warning_count=1,
            expected_warning_severity=WarningSeverity.ERROR,
            expected_cte_bodies={
                "orders": "SELECT 1",
            },
        ),
        PlanTestChainTestCase(
            description=("unresolved seed produces error warning"),
            model_queries={
                "orders": ('SELECT code FROM __seed("missing_seed")'),
            },
            mock_ref_ctes={},
            mock_source_ctes={},
            helper_ctes={},
            expected_model_names=("orders",),
            expected_chain_length=1,
            expected_warning_count=1,
            expected_warning_severity=WarningSeverity.ERROR,
            expected_cte_bodies={
                "orders": "SELECT 1",
            },
        ),
        PlanTestChainTestCase(
            description=("model with both mock ref and chain ref resolves both"),
            model_queries={
                "stg": 'SELECT id FROM __source("raw")',
                "final": ('SELECT a.id FROM __ref("stg") a JOIN __ref("lookup") b ON a.id = b.id'),
            },
            mock_ref_ctes={
                "lookup": "SELECT 1 AS id, 'US' AS country",
            },
            mock_source_ctes={
                "raw": "SELECT 1 AS id",
            },
            helper_ctes={},
            expected_model_names=("stg", "final"),
            expected_chain_length=2,
            expected_sql_fragments={
                "final": "SELECT 1 AS id",
            },
            expected_warning_count=0,
            expected_cte_bodies={
                "stg": "SELECT 1 AS id",
                "final": "SELECT 1 AS id",
            },
        ),
        PlanTestChainTestCase(
            description=("multiple unresolved refs produce multiple errors"),
            model_queries={
                "orders": ('SELECT a.id FROM __ref("x") a JOIN __source("y") b ON a.id = b.id'),
            },
            mock_ref_ctes={},
            mock_source_ctes={},
            helper_ctes={},
            expected_model_names=("orders",),
            expected_chain_length=1,
            expected_warning_count=2,
            expected_warning_severity=WarningSeverity.ERROR,
            expected_cte_bodies={
                "orders": "SELECT 1",
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_test_and_project_when_planning_then_produces_expected_chain(
    test_case: PlanTestChainTestCase,
) -> None:
    compiled_test: CompiledSqlTest
    project: CompiledProject
    compiled_test, project = build_test_and_project(test_case)

    entry: SqlTestPlanEntry
    warnings: tuple[PlanWarning, ...]
    entry, warnings = plan_test(test=compiled_test, project=project, adapter=DuckDbAdapter())

    assert len(entry.chain) == test_case.expected_chain_length

    model_name: str
    expected_fragment: str
    for model_name, expected_fragment in test_case.expected_sql_fragments.items():
        matching: list[ChainStep] = [s for s in entry.chain if s.model_name == model_name]
        assert len(matching) == 1
        assert expected_fragment in matching[0].resolved_sql

    assert len(warnings) == test_case.expected_warning_count
    expected_sev: WarningSeverity | None = test_case.expected_warning_severity
    actual_sevs: tuple[WarningSeverity, ...] = tuple(w.severity for w in warnings)
    assert (expected_sev is None) or all(s == expected_sev for s in actual_sevs)
    expected_error_fragments: tuple[str, ...] = (
        () if test_case.expected_error_fragment is None else (test_case.expected_error_fragment,)
    )
    expected_error_fragment: str
    for expected_error_fragment in expected_error_fragments:
        assert any(expected_error_fragment in w.message for w in warnings)


@pytest.mark.parametrize(
    "test_case",
    [
        PlanMacroTestCase(
            description="plans macro test as one direct comparison chain step with helpers",
            helper_ctes={"input_values": "SELECT '  PAID  ' AS raw_status"},
            actual_sql="SELECT LOWER(TRIM(raw_status)) AS status FROM input_values",
            expected_sql="SELECT 'paid' AS status",
            expected_actual_fragment="SELECT LOWER(TRIM(raw_status)) AS status FROM input_values",
            expected_expected_fragment="SELECT 'paid' AS status",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_macro_sql_test_when_planning_then_compares_actual_to_expected_directly(
    test_case: PlanMacroTestCase,
) -> None:
    test_file: DiscoveredSqlTestFile = DiscoveredSqlTestFile(
        file_path=Path("tests/unit/test_macro.sql"),
        relative_path=Path("tests/unit/test_macro.sql"),
        contents="",
        blocks=(),
    )
    test_block: DiscoveredSqlTestBlock = DiscoveredSqlTestBlock(
        test_index=1,
        header_values={"mode": "macro", "name": "normalizes status"},
        sql_body="",
        name="normalizes status",
        mode=SqlTestMode.MACRO,
    )
    helper_ctes: tuple[CompileSqlTestCte, ...] = tuple(
        CompileSqlTestCte(name=name, sql_body=sql) for name, sql in test_case.helper_ctes.items()
    )
    sql_test: CompiledSqlTest = CompiledSqlTest(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_TEST,
            name="normalizes status",
        ),
        scope_deps=(CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),),
        name="normalizes status",
        test_file=test_file,
        test_block=test_block,
        sql_body="",
        mode=SqlTestMode.MACRO,
        payload=CompiledDirectLogicSqlTestPayload(
            mode=SqlTestMode.MACRO,
            helper_ctes=helper_ctes,
            actual_cte=CompileSqlTestCte(
                name="__macro_actual__",
                sql_body=test_case.actual_sql,
            ),
            expected_cte=CompileSqlTestCte(
                name="__macro_expected__",
                sql_body=test_case.expected_sql,
            ),
            tested_resource_names=("normalize_status",),
        ),
    )

    entry, warnings = plan_test(
        test=sql_test,
        adapter=DuckDbAdapter(),
        project=CompiledProject(
            run_id="test_run",
            effective_target_name=None,
            effective_connection={},
            effective_vars={},
        ),
    )

    assert warnings == ()
    assert len(entry.chain) == 1
    assert entry.chain[0].model_name == "macro normalizes status"
    assert test_case.expected_actual_fragment in entry.chain[0].resolved_sql
    assert entry.chain[0].expected_cte_sql is not None
    assert test_case.expected_expected_fragment in entry.chain[0].expected_cte_sql


@pytest.mark.parametrize(
    "test_case",
    [
        PlanMacroTestCase(
            description="plans udf test as one direct comparison chain step with resolved udf call",
            helper_ctes={"input_values": "SELECT 1250 AS amount_cents"},
            actual_sql='SELECT __udf("format_cents")(amount_cents) AS formatted FROM input_values',
            expected_sql="SELECT '$12.50' AS formatted",
            expected_actual_fragment="main.format_cents(amount_cents) AS formatted",
            expected_expected_fragment="SELECT '$12.50' AS formatted",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_udf_sql_test_when_planning_then_compares_resolved_actual_to_expected_directly(
    test_case: PlanMacroTestCase,
) -> None:
    test_file: DiscoveredSqlTestFile = DiscoveredSqlTestFile(
        file_path=Path("tests/unit/test_udf.sql"),
        relative_path=Path("tests/unit/test_udf.sql"),
        contents="",
        blocks=(),
    )
    test_block: DiscoveredSqlTestBlock = DiscoveredSqlTestBlock(
        test_index=1,
        header_values={"mode": "udf", "name": "formats cents"},
        sql_body="",
        name="formats cents",
        mode=SqlTestMode.UDF,
    )
    helper_ctes: tuple[CompileSqlTestCte, ...] = tuple(
        CompileSqlTestCte(name=name, sql_body=sql) for name, sql in test_case.helper_ctes.items()
    )
    sql_test: CompiledSqlTest = CompiledSqlTest(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_TEST,
            name="formats cents",
        ),
        scope_deps=(CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),),
        name="formats cents",
        test_file=test_file,
        test_block=test_block,
        sql_body="",
        mode=SqlTestMode.UDF,
        payload=CompiledDirectLogicSqlTestPayload(
            mode=SqlTestMode.UDF,
            helper_ctes=helper_ctes,
            actual_cte=CompileSqlTestCte(
                name="__udf_actual__",
                sql_body=test_case.actual_sql,
            ),
            expected_cte=CompileSqlTestCte(
                name="__udf_expected__",
                sql_body=test_case.expected_sql,
            ),
            tested_resource_names=("format_cents",),
        ),
    )

    entry, warnings = plan_test(
        test=sql_test,
        adapter=DuckDbAdapter(),
        project=CompiledProject(
            run_id="test_run",
            effective_target_name=None,
            effective_connection={},
            effective_vars={},
            functions=(
                CompiledFunction(
                    key=CompiledObjectKey(
                        resource_type=CompiledResourceType.UDF,
                        name="format_cents",
                    ),
                    deps=(),
                    name="format_cents",
                    relative_path=Path("functions/sql/format_cents.sql"),
                    arguments=(),
                    returns="VARCHAR",
                    body_sql="",
                    destination=CompiledRelationLocation(
                        database=None,
                        schema="main",
                        name="format_cents",
                        qualified_name="main.format_cents",
                    ),
                    fingerprint_destination=CompiledRelationLocation(
                        database=None,
                        schema="main",
                        name="format_cents__fingerprint",
                        qualified_name="main.format_cents__fingerprint",
                    ),
                ),
            ),
        ),
    )

    assert warnings == ()
    assert len(entry.chain) == 1
    assert entry.chain[0].model_name == "udf formats cents"
    assert test_case.expected_actual_fragment in entry.chain[0].resolved_sql
    assert entry.chain[0].expected_cte_sql is not None
    assert test_case.expected_expected_fragment in entry.chain[0].expected_cte_sql


@pytest.mark.parametrize(
    "test_case",
    [
        PlanMacroTestCase(
            description=(
                "plans table function test as one direct comparison chain step with resolved call"
            ),
            helper_ctes={},
            actual_sql='SELECT customer_id, order_id FROM __table_fn("customer_orders")(42)',
            expected_sql="SELECT 42 AS customer_id, 1 AS order_id",
            expected_actual_fragment="FROM main.customer_orders(42)",
            expected_expected_fragment="SELECT 42 AS customer_id, 1 AS order_id",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_table_function_sql_test_when_planning_then_compares_resolved_actual_to_expected(
    test_case: PlanMacroTestCase,
) -> None:
    test_file: DiscoveredSqlTestFile = DiscoveredSqlTestFile(
        file_path=Path("tests/unit/test_table_fn.sql"),
        relative_path=Path("tests/unit/test_table_fn.sql"),
        contents="",
        blocks=(),
    )
    test_block: DiscoveredSqlTestBlock = DiscoveredSqlTestBlock(
        test_index=1,
        header_values={"mode": "table_fn", "name": "returns customer orders"},
        sql_body="",
        name="returns customer orders",
        mode=SqlTestMode.TABLE_FN,
    )
    sql_test: CompiledSqlTest = CompiledSqlTest(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_TEST,
            name="returns customer orders",
        ),
        scope_deps=(
            CompiledObjectKey(resource_type=CompiledResourceType.TABLE_FN, name="customer_orders"),
        ),
        name="returns customer orders",
        test_file=test_file,
        test_block=test_block,
        sql_body="",
        mode=SqlTestMode.TABLE_FN,
        payload=CompiledDirectLogicSqlTestPayload(
            mode=SqlTestMode.TABLE_FN,
            helper_ctes=(),
            actual_cte=CompileSqlTestCte(
                name="__table_fn_actual__",
                sql_body=test_case.actual_sql,
            ),
            expected_cte=CompileSqlTestCte(
                name="__table_fn_expected__",
                sql_body=test_case.expected_sql,
            ),
            tested_resource_names=("customer_orders",),
        ),
    )

    entry, warnings = plan_test(
        test=sql_test,
        adapter=DuckDbAdapter(),
        project=CompiledProject(
            run_id="test_run",
            effective_target_name=None,
            effective_connection={},
            effective_vars={},
            functions=(
                CompiledFunction(
                    key=CompiledObjectKey(
                        resource_type=CompiledResourceType.TABLE_FN,
                        name="customer_orders",
                    ),
                    deps=(),
                    name="customer_orders",
                    relative_path=Path("functions/sql/customer_orders.sql"),
                    arguments=(),
                    returns="TABLE",
                    body_sql="",
                    destination=CompiledRelationLocation(
                        database=None,
                        schema="main",
                        name="customer_orders",
                        qualified_name="main.customer_orders",
                    ),
                    fingerprint_destination=CompiledRelationLocation(
                        database=None,
                        schema="main",
                        name="customer_orders__fingerprint",
                        qualified_name="main.customer_orders__fingerprint",
                    ),
                ),
            ),
        ),
    )

    assert warnings == ()
    assert len(entry.chain) == 1
    assert entry.chain[0].model_name == "table_fn returns customer orders"
    assert test_case.expected_actual_fragment in entry.chain[0].resolved_sql
    assert entry.chain[0].expected_cte_sql is not None
    assert test_case.expected_expected_fragment in entry.chain[0].expected_cte_sql


@pytest.mark.parametrize(
    "test_case",
    [
        PlanTestChainTestCase(
            description="sql_analysis path lifts refs and sources into readable top-level ctes",
            model_queries={
                "stg_orders": 'SELECT id, amount FROM __source("raw")',
                "fact_orders": (
                    "WITH local_helper AS (SELECT 1 AS one) "
                    "SELECT id, amount + one AS adjusted "
                    'FROM __ref("stg_orders") CROSS JOIN local_helper'
                ),
            },
            mock_ref_ctes={},
            mock_source_ctes={"raw": "SELECT 1 AS id, 100 AS amount"},
            helper_ctes={},
            expected_model_names=("stg_orders", "fact_orders"),
            expected_chain_length=2,
            expected_cte_bodies={
                "stg_orders": "SELECT 1 AS id, 100 AS amount",
                "fact_orders": "SELECT 1 AS id, 101 AS adjusted",
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_analysis_enabled_when_planning_test_then_it_uses_top_level_generated_ctes(
    test_case: PlanTestChainTestCase,
) -> None:
    compiled_test: CompiledSqlTest
    project: CompiledProject
    compiled_test, project = build_test_and_project(test_case)

    entry: SqlTestPlanEntry
    warnings: tuple[PlanWarning, ...]
    entry, warnings = plan_test(
        test=compiled_test,
        project=project,
        adapter=DuckDbAdapter(),
        sql_analysis_enabled=True,
    )

    assert not warnings
    assert len(entry.chain) == test_case.expected_chain_length
    step_map: dict[str, ChainStep] = {step.model_name: step for step in entry.chain}
    assert (
        "WITH __source__raw AS (SELECT 1 AS id, 100 AS amount)"
        in step_map["stg_orders"].resolved_sql
    )
    assert "FROM __source__raw" in step_map["stg_orders"].resolved_sql
    assert (
        "WITH __source__raw AS (SELECT 1 AS id, 100 AS amount), "
        "__ref__stg_orders AS (SELECT id, amount FROM __source__raw)"
        in step_map["fact_orders"].resolved_sql
    )
    assert "__ref__stg_orders AS (WITH" not in step_map["fact_orders"].resolved_sql
    assert "local_helper AS (SELECT 1 AS one)" in step_map["fact_orders"].resolved_sql
    assert "FROM __ref__stg_orders CROSS JOIN local_helper" in step_map["fact_orders"].resolved_sql


@pytest.mark.parametrize(
    "test_case",
    [
        PlanTestChainTestCase(
            description="sql_analysis path errors on generated cte name collision",
            model_queries={
                "orders": 'WITH __source__raw AS (SELECT 9 AS id) SELECT id FROM __source("raw")',
            },
            mock_ref_ctes={},
            mock_source_ctes={"raw": "SELECT 1 AS id"},
            helper_ctes={},
            expected_model_names=("orders",),
            expected_chain_length=1,
            expected_error_fragment="conflicts with the generated source CTE",
            expected_cte_bodies={"orders": "SELECT 1 AS id"},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_analysis_enabled_when_generated_cte_name_conflicts_then_it_raises_clear_error(
    test_case: PlanTestChainTestCase,
) -> None:
    compiled_test: CompiledSqlTest
    project: CompiledProject
    compiled_test, project = build_test_and_project(test_case)

    assert test_case.expected_error_fragment is not None
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        plan_test(
            test=compiled_test,
            project=project,
            adapter=DuckDbAdapter(),
            sql_analysis_enabled=True,
        )
