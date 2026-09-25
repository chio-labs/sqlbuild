from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile._helpers.attachment.sql_tests import build_scenario_inputs
from sqlbuild.compiler.compile._helpers.scenarios.core import (
    extract_sql_scenario_ctes,
    extract_sql_scenario_expected_model_names,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompileSqlScenarioCtes,
    CompileSqlScenarioInput,
    MacroContext,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSourceFile,
    DiscoveredSqlScenarioFile,
)
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig, SourceEntry
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    BuildScenarioInputsErrorTestCase,
    BuildScenarioInputsTestCase,
    CteScannerMessageTestCase,
    ExtractSqlScenarioCtesErrorTestCase,
    ExtractSqlScenarioCtesTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import (
    DUCKDB_DECLARATION_EXPANSION_CONTEXT,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExtractSqlScenarioCtesTestCase(
            description="extracts dbt ref fixtures",
            sql="""
        WITH
        __dbt_ref__orders AS (SELECT 1 AS order_id),
        __dbt_ref__stripe__payments AS (SELECT 1 AS payment_id),
        __expected__fact_orders AS (SELECT 1 AS order_id)
        SELECT 1
        """.strip(),
            expected_authored_cte_names=("__dbt_ref__orders", "__dbt_ref__stripe__payments"),
            expected_source_fixture_names=(),
            expected_ref_fixture_names=(),
            expected_dbt_ref_fixture_names=("orders", "stripe__payments"),
            expected_expected_model_names=("fact_orders",),
            expected_assertion_names=(),
        ),
        ExtractSqlScenarioCtesTestCase(
            description="extracts source ref seed fixtures expectations and assertions",
            sql="""
        WITH
        helper_customers AS (SELECT 10 AS customer_id),
        __source__raw__orders AS (SELECT 1 AS order_id, 10 AS customer_id),
        __ref__stg_customers AS (SELECT customer_id FROM helper_customers),
        __seed__waffle_types AS (SELECT 1 AS waffle_type_id),
        __expected__daily_revenue AS (SELECT 1 AS order_id),
        __assert__no_negative_revenue AS (
          SELECT * FROM __ref(daily_revenue) WHERE revenue < 0
        )
        SELECT 1
        """.strip(),
            expected_authored_cte_names=(
                "helper_customers",
                "__source__raw__orders",
                "__ref__stg_customers",
                "__seed__waffle_types",
            ),
            expected_source_fixture_names=("raw__orders",),
            expected_ref_fixture_names=("stg_customers",),
            expected_seed_fixture_names=("waffle_types",),
            expected_expected_model_names=("daily_revenue",),
            expected_assertion_names=("no_negative_revenue",),
        ),
        ExtractSqlScenarioCtesTestCase(
            description="allows assertion only scenario target inference later",
            sql="""
        WITH
        __source__raw__orders AS (SELECT 1 AS order_id),
        __assert__has_no_null_orders AS (
          SELECT * FROM __ref(fact_orders) WHERE order_id IS NULL
        )
        SELECT 1
        """.strip(),
            expected_authored_cte_names=("__source__raw__orders",),
            expected_source_fixture_names=("raw__orders",),
            expected_ref_fixture_names=(),
            expected_expected_model_names=(),
            expected_assertion_names=("has_no_null_orders",),
        ),
        ExtractSqlScenarioCtesTestCase(
            description="allows expected only scenario with ref fixture",
            sql="""
        WITH
        __ref__orders_base AS (SELECT 1 AS order_id),
        __expected__fact_orders AS (SELECT 1 AS order_id)
        SELECT 1
        """.strip(),
            expected_authored_cte_names=("__ref__orders_base",),
            expected_source_fixture_names=(),
            expected_ref_fixture_names=("orders_base",),
            expected_expected_model_names=("fact_orders",),
            expected_assertion_names=(),
        ),
        ExtractSqlScenarioCtesTestCase(
            description="allows expected only scenario with seed fixture",
            sql="""
        WITH
        __seed__country_codes AS (SELECT 'US' AS country_code),
        __expected__dim_countries AS (SELECT 'US' AS country_code)
        SELECT 1
        """.strip(),
            expected_authored_cte_names=("__seed__country_codes",),
            expected_source_fixture_names=(),
            expected_ref_fixture_names=(),
            expected_seed_fixture_names=("country_codes",),
            expected_expected_model_names=("dim_countries",),
            expected_assertion_names=(),
        ),
        ExtractSqlScenarioCtesTestCase(
            description="extracts scenario ctes with sql_analysis fallback syntax",
            sql="""
        WITH
        "__source__raw__orders" AS MATERIALIZED (SELECT 1 AS order_id),
        "__expected__daily_revenue" AS (SELECT order_id FROM "__source__raw__orders")
        SELECT 1
        """.strip(),
            expected_authored_cte_names=("__source__raw__orders",),
            expected_source_fixture_names=("raw__orders",),
            expected_ref_fixture_names=(),
            expected_seed_fixture_names=(),
            expected_expected_model_names=("daily_revenue",),
            expected_assertion_names=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_scenario_cte_variants_when_extracting_then_it_returns_expected_roles(
    test_case: ExtractSqlScenarioCtesTestCase,
) -> None:
    extracted_ctes: CompileSqlScenarioCtes = extract_sql_scenario_ctes(
        sql=test_case.sql,
        file_label="tests/scenarios/revenue__customer_refund.sql",
    )

    assert (
        tuple(cte.name for cte in extracted_ctes.authored_ctes)
        == test_case.expected_authored_cte_names
    )
    assert extracted_ctes.source_fixture_names == test_case.expected_source_fixture_names
    assert extracted_ctes.ref_fixture_names == test_case.expected_ref_fixture_names
    assert extracted_ctes.seed_fixture_names == test_case.expected_seed_fixture_names
    assert extracted_ctes.dbt_ref_fixture_names == test_case.expected_dbt_ref_fixture_names
    assert extracted_ctes.expected_model_names == test_case.expected_expected_model_names
    assert extracted_ctes.assertion_names == test_case.expected_assertion_names


@pytest.mark.parametrize(
    "test_case",
    [
        ExtractSqlScenarioCtesErrorTestCase(
            description="raises when ceremonial select is wrapped in a final result cte",
            sql="""
        WITH
        __ref__orders_base AS (SELECT 1 AS order_id),
        __expected__fact_orders AS (SELECT 1 AS order_id),
        scenario_result AS (SELECT 1)
        SELECT * FROM scenario_result
        """.strip(),
            expected_error_fragment="must end with a ceremonial top-level `SELECT 1`",
        ),
        ExtractSqlScenarioCtesErrorTestCase(
            description="raises when assertion depends directly on expected result",
            sql="""
        WITH
        __source__raw__orders AS (SELECT 1 AS order_id),
        __expected__orders AS (SELECT 1 AS order_id),
        __assert__expected_is_nonempty AS (SELECT * FROM __expected__orders)
        SELECT 1
        """.strip(),
            expected_error_fragment=(
                "'__assert__expected_is_nonempty' must not depend on '__expected__orders'"
            ),
        ),
        ExtractSqlScenarioCtesErrorTestCase(
            description="raises when expected result depends indirectly on assertion",
            sql="""
        WITH
        __source__raw__orders AS (SELECT 1 AS order_id),
        __assert__positive_order_id AS (SELECT 1 AS order_id WHERE order_id < 1),
        assertion_helper AS (SELECT * FROM __assert__positive_order_id),
        __expected__orders AS (SELECT * FROM assertion_helper)
        SELECT 1
        """.strip(),
            expected_error_fragment=(
                "'__expected__orders' must not depend on "
                "'__assert__positive_order_id' through 'assertion_helper'"
            ),
        ),
        ExtractSqlScenarioCtesErrorTestCase(
            description="raises when scenario has no fixture ctes",
            sql="""
        WITH __expected__fact_orders AS (SELECT 1 AS order_id)
        SELECT 1
        """.strip(),
            expected_error_fragment=(
                r"must define at least one __source__\*, __ref__\*, __seed__\*, "
                r"or __dbt_ref__\* fixture CTE"
            ),
        ),
        ExtractSqlScenarioCtesErrorTestCase(
            description="raises when scenario has no expected or assertion ctes",
            sql="""
        WITH __source__raw__orders AS (SELECT 1 AS order_id)
        SELECT 1
        """.strip(),
            expected_error_fragment=(
                "must define at least one __expected__<model> or __assert__<assertion>"
            ),
        ),
        ExtractSqlScenarioCtesErrorTestCase(
            description="raises when scenario uses macro mock cte",
            sql="""
        WITH
        __source__raw__orders AS (SELECT 1 AS order_id),
        __macro__country AS (SELECT '''US'''),
        __expected__fact_orders AS (SELECT 1 AS order_id)
        SELECT 1
        """.strip(),
            expected_error_fragment="does not support macro mock CTE '__macro__country'",
        ),
        ExtractSqlScenarioCtesErrorTestCase(
            description="raises when assertion cte suffix is missing",
            sql="""
        WITH
        __source__raw__orders AS (SELECT 1 AS order_id),
        __assert__ AS (SELECT * FROM __ref(fact_orders))
        SELECT 1
        """.strip(),
            expected_error_fragment="__assert__<assertion>",
        ),
        ExtractSqlScenarioCtesErrorTestCase(
            description="raises when duplicate cte names are present",
            sql="""
        WITH
        __source__raw__orders AS (SELECT 1 AS order_id),
        __source__raw__orders AS (SELECT 2 AS order_id),
        __expected__fact_orders AS (SELECT 1 AS order_id)
        SELECT 1
        """.strip(),
            expected_error_fragment="defines duplicate CTE '__source__raw__orders'",
        ),
        ExtractSqlScenarioCtesErrorTestCase(
            description="raises when fallback terminal read follows a set operation",
            sql="""
        WITH
        "__ref__orders_base" AS (SELECT 1 AS order_id),
        "__expected__fact_orders" AS (SELECT 1 AS order_id),
        scenario_result AS (SELECT 1)
        SELECT 2 UNION ALL SELECT * FROM scenario_result
        """.strip(),
            expected_error_fragment="expected a CTE name",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sql_scenario_ctes_when_extracting_then_it_raises_clear_errors(
    test_case: ExtractSqlScenarioCtesErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        extract_sql_scenario_ctes(
            sql=test_case.sql,
            file_label="tests/scenarios/revenue__customer_refund.sql",
        )


@pytest.mark.parametrize(
    "test_case",
    [
        BuildScenarioInputsTestCase(
            description="attaches scenario cte roles after authored sql expansion",
            sql_body="""
        WITH
        __source__raw__orders AS (SELECT @@customer_id AS customer_id),
        __expected__daily_revenue AS (SELECT @@customer_id AS customer_id)
        SELECT 1
        """.strip(),
            effective_vars={"customer_id": "10"},
            expected_source_fixture_names=("raw__orders",),
            expected_ref_fixture_names=(),
            expected_seed_fixture_names=(),
            expected_expected_model_names=("daily_revenue",),
            expected_assertion_names=(),
            expected_sql_fragment="SELECT 10 AS customer_id",
        ),
        BuildScenarioInputsTestCase(
            description="attaches seed only scenario fixture roles",
            sql_body="""
        WITH
        __seed__country_codes AS (SELECT '@@country_code' AS country_code),
        __expected__dim_countries AS (SELECT '@@country_code' AS country_code)
        SELECT 1
        """.strip(),
            effective_vars={"country_code": "US"},
            expected_source_fixture_names=(),
            expected_ref_fixture_names=(),
            expected_seed_fixture_names=("country_codes",),
            expected_expected_model_names=("dim_countries",),
            expected_assertion_names=(),
            expected_sql_fragment="SELECT 'US' AS country_code",
        ),
        BuildScenarioInputsTestCase(
            description="allows project source references in scenario fixture ctes",
            sql_body="""
        WITH
        __source__raw__orders AS (
          SELECT order_id FROM __source("raw__orders") WHERE order_id <= 10
        ),
        __expected__daily_revenue AS (SELECT 1 AS order_id)
        SELECT 1
        """.strip(),
            effective_vars={},
            expected_source_fixture_names=("raw__orders",),
            expected_ref_fixture_names=(),
            expected_seed_fixture_names=(),
            expected_expected_model_names=("daily_revenue",),
            expected_assertion_names=(),
            expected_sql_fragment='__source("raw__orders")',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_discovered_scenario_when_building_scenario_inputs_then_it_attaches_cte_roles(
    test_case: BuildScenarioInputsTestCase,
) -> None:
    scenario_file: DiscoveredSqlScenarioFile = DiscoveredSqlScenarioFile(
        file_path=Path(__file__),
        relative_path=Path("tests/scenarios/revenue__customer_refund.sql"),
        contents="",
        header_values={},
        name="revenue__customer_refund",
        sql_body=test_case.sql_body,
    )
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(name="demo", adapter="duckdb"),
        local_config=LocalConfig(),
        scenario_files=(scenario_file,),
        source_files=(
            DiscoveredSourceFile(
                file_path=Path("sources/raw.yml"),
                relative_path=Path("sources/raw.yml"),
                contents="",
                source_entries=(SourceEntry(name="raw__orders", schema="raw", table="orders"),),
            ),
        ),
    )

    scenario_inputs: tuple[CompileSqlScenarioInput, ...] = build_scenario_inputs(
        discovered_inputs=discovered_inputs,
        effective_vars=test_case.effective_vars,
        macro_context=MacroContext(
            adapter_name="duckdb", sql_analysis_enabled=True, target_name=None
        ),
        loaded_macros={},
        declaration_expansion=DUCKDB_DECLARATION_EXPANSION_CONTEXT,
    )

    assert len(scenario_inputs) == 1
    scenario_input: CompileSqlScenarioInput = scenario_inputs[0]
    assert scenario_input.scenario_file.name == "revenue__customer_refund"
    assert scenario_input.source_fixture_names == test_case.expected_source_fixture_names
    assert scenario_input.ref_fixture_names == test_case.expected_ref_fixture_names
    assert scenario_input.seed_fixture_names == test_case.expected_seed_fixture_names
    assert scenario_input.dbt_ref_fixture_names == test_case.expected_dbt_ref_fixture_names
    assert scenario_input.expected_model_names == test_case.expected_expected_model_names
    assert scenario_input.assertion_names == test_case.expected_assertion_names
    assert test_case.expected_sql_fragment in scenario_input.sql_body


@pytest.mark.parametrize(
    "test_case",
    [
        BuildScenarioInputsErrorTestCase(
            description="rejects project source references in expected ctes",
            sql_body="""
        WITH
        __source__raw__orders AS (SELECT 1 AS order_id),
        __expected__daily_revenue AS (SELECT order_id FROM __source("raw__orders"))
        SELECT 1
        """.strip(),
            expected_error_fragment="__expected__daily_revenue.*must not reference project source",
        ),
        BuildScenarioInputsErrorTestCase(
            description="rejects unknown project source references in fixture ctes",
            sql_body="""
        WITH
        __source__raw__orders AS (SELECT order_id FROM __source("missing_source")),
        __expected__daily_revenue AS (SELECT 1 AS order_id)
        SELECT 1
        """.strip(),
            expected_error_fragment="references unknown source 'missing_source'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_scenario_source_refs_when_building_inputs_then_it_raises_clear_error(
    test_case: BuildScenarioInputsErrorTestCase,
) -> None:
    scenario_file: DiscoveredSqlScenarioFile = DiscoveredSqlScenarioFile(
        file_path=Path(__file__),
        relative_path=Path("tests/scenarios/revenue__customer_refund.sql"),
        contents="",
        header_values={},
        name="revenue__customer_refund",
        sql_body=test_case.sql_body,
    )
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(name="demo", adapter="duckdb"),
        local_config=LocalConfig(),
        scenario_files=(scenario_file,),
        source_files=(
            DiscoveredSourceFile(
                file_path=Path("sources/raw.yml"),
                relative_path=Path("sources/raw.yml"),
                contents="",
                source_entries=(SourceEntry(name="raw__orders", schema="raw", table="orders"),),
            ),
        ),
    )

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        build_scenario_inputs(
            discovered_inputs=discovered_inputs,
            effective_vars={},
            macro_context=MacroContext(
                adapter_name="duckdb", sql_analysis_enabled=True, target_name=None
            ),
            loaded_macros={},
            declaration_expansion=DUCKDB_DECLARATION_EXPANSION_CONTEXT,
        )


@pytest.mark.parametrize(
    "test_case",
    (
        CteScannerMessageTestCase(
            description="scenario without a with clause uses scenario wording",
            sql="SELECT * FROM orders",
            expected_message=(
                "SQL scenario 'tests/scenarios/orders.sql' must declare fixture CTEs and at least "
                "one __expected__<model> or __assert__<assertion> CTE before `SELECT 1`"
            ),
        ),
        CteScannerMessageTestCase(
            description="unclosed comment before a fixture uses scenario wording",
            sql="WITH /* unfinished",
            expected_message="SQL scenario contains an unclosed block comment",
        ),
        CteScannerMessageTestCase(
            description="unclosed trailing comment uses scenario wording",
            sql="WITH __expected__orders AS (SELECT 1 AS order_id) SELECT 1; /* unfinished",
            expected_message="SQL scenario contains an unclosed block comment",
        ),
        CteScannerMessageTestCase(
            description="scenario with an invalid cte name uses scenario wording",
            sql="WITH 1orders AS (SELECT 1) SELECT 1",
            expected_message="SQL scenario 'tests/scenarios/orders.sql' expected a CTE name",
        ),
        CteScannerMessageTestCase(
            description="scenario without a ceremonial select uses scenario wording",
            sql=(
                "WITH __source__raw_orders AS (SELECT 1 AS order_id), "
                "__expected__orders AS (SELECT 1 AS order_id), "
                "result AS (SELECT 1) SELECT * FROM result"
            ),
            expected_message=(
                "SQL scenario 'tests/scenarios/orders.sql' must end with a ceremonial top-level "
                "`SELECT 1` after its CTEs"
            ),
        ),
        CteScannerMessageTestCase(
            description="scenario fixture without a target uses scenario wording",
            sql=(
                "WITH __source__ AS (SELECT 1 AS order_id), "
                "__expected__orders AS (SELECT 1 AS order_id) SELECT 1"
            ),
            expected_message=(
                "SQL scenario 'tests/scenarios/orders.sql' must use __source__<source> to "
                "identify a target"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_malformed_scenario_ctes_when_extracting_then_messages_name_the_scenario(
    test_case: CteScannerMessageTestCase,
) -> None:
    with pytest.raises(CompileInputError) as error_info:
        _ = extract_sql_scenario_ctes(sql=test_case.sql, file_label="tests/scenarios/orders.sql")

    assert str(error_info.value) == test_case.expected_message


@pytest.mark.parametrize(
    "test_case",
    (
        CteScannerMessageTestCase(
            description="expected model scan without AS uses scenario wording",
            sql="WITH __source__raw_orders (SELECT 1 AS order_id) SELECT 1",
            expected_message="SQL scenario 'tests/scenarios/orders.sql' expected keyword AS",
        ),
        CteScannerMessageTestCase(
            description="expected model scan unclosed comment uses scenario wording",
            sql="WITH /* unfinished",
            expected_message="SQL scenario contains an unclosed block comment",
        ),
        CteScannerMessageTestCase(
            description="expected model scan leading unclosed comment uses scenario wording",
            sql="/* unfinished",
            expected_message="SQL scenario contains an unclosed block comment",
        ),
        CteScannerMessageTestCase(
            description="expected model scan without a target uses scenario wording",
            sql=(
                "WITH __source__raw_orders AS (SELECT 1 AS order_id), "
                "__expected__ AS (SELECT 1 AS order_id) SELECT 1"
            ),
            expected_message=(
                "SQL scenario 'tests/scenarios/orders.sql' must use __expected__<model> to "
                "identify a target"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_malformed_scenario_ctes_when_scanning_expected_models_then_names_the_scenario(
    test_case: CteScannerMessageTestCase,
) -> None:
    with pytest.raises(CompileInputError) as error_info:
        _ = extract_sql_scenario_expected_model_names(
            sql=test_case.sql, file_label="tests/scenarios/orders.sql"
        )

    assert str(error_info.value) == test_case.expected_message
