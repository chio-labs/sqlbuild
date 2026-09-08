"""Behavior tests for selected built-in policy rules."""

from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.policy_engine.main.evaluate import evaluate
from sqlbuild.policy_engine.models import (
    PolicyConfig,
    PolicyResult,
    SelectStarAllow,
)
from tests.unit.src.sqlbuild.policy_engine.main.evaluate._test_types import (
    PolicyEvaluationTestCase,
)
from tests.unit.src.sqlbuild.policy_engine.main.evaluate.helpers import build_project


@pytest.mark.parametrize(
    "test_case",
    (
        PolicyEvaluationTestCase(
            description="empty selection disables policy",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="SELECT * FROM raw.prices",
            config_values={},
            select=(),
            expected_codes=(),
        ),
        PolicyEvaluationTestCase(
            description="contract rule faults missing enforced contract",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="WITH prices AS (SELECT id FROM source_prices) SELECT id FROM prices",
            config_values={"materialized": "table"},
            select=("SQBPC101",),
            expected_codes=("SQBPC101",),
        ),
        PolicyEvaluationTestCase(
            description="direct enum member comparison passes",
            model_name="market__int_clean__prices",
            relative_path="models/intermediate/market__int_clean__prices.sql",
            sql=(
                'WITH upstream AS (SELECT * FROM __ref("market__stg__prices")), '
                "filtered AS (SELECT status FROM upstream WHERE upstream.status = 'win') "
                "SELECT status FROM filtered"
            ),
            authored_sql=(
                'WITH upstream AS (SELECT * FROM __ref("market__stg__prices")), '
                "filtered AS (SELECT status FROM upstream "
                'WHERE upstream.status = @enum("status").WIN) SELECT status FROM filtered'
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD101",),
            expected_codes=(),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
            enum_columns=("status",),
        ),
        PolicyEvaluationTestCase(
            description="modified controlled enum column faults",
            model_name="market__int_clean__prices",
            relative_path="models/intermediate/market__int_clean__prices.sql",
            sql=(
                'WITH upstream AS (SELECT * FROM __ref("market__stg__prices")), '
                "filtered AS (SELECT status FROM upstream "
                "WHERE LOWER(upstream.status) = 'win') SELECT status FROM filtered"
            ),
            authored_sql=(
                'WITH upstream AS (SELECT * FROM __ref("market__stg__prices")), '
                "filtered AS (SELECT status FROM upstream "
                'WHERE LOWER(upstream.status) = @enum("status").WIN) '
                "SELECT status FROM filtered"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD101",),
            expected_codes=("SQBPD101",),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
            enum_columns=("status",),
        ),
        PolicyEvaluationTestCase(
            description="uppercased controlled enum column faults",
            model_name="market__int_clean__prices",
            relative_path="models/intermediate/market__int_clean__prices.sql",
            sql=(
                'SELECT status FROM __ref("market__stg__prices") AS upstream '
                "WHERE UPPER(upstream.status) = 'win'"
            ),
            authored_sql=(
                'SELECT status FROM __ref("market__stg__prices") AS upstream '
                'WHERE UPPER(upstream.status) = @enum("status").WIN'
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD101",),
            expected_codes=("SQBPD101",),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
            enum_columns=("status",),
        ),
        PolicyEvaluationTestCase(
            description="cast controlled enum column faults",
            model_name="market__int_clean__prices",
            relative_path="models/intermediate/market__int_clean__prices.sql",
            sql=(
                'SELECT status FROM __ref("market__stg__prices") AS upstream '
                "WHERE CAST(upstream.status AS VARCHAR) = 'win'"
            ),
            authored_sql=(
                'SELECT status FROM __ref("market__stg__prices") AS upstream '
                'WHERE CAST(upstream.status AS VARCHAR) = @enum("status").WIN'
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD101",),
            expected_codes=("SQBPD101",),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
            enum_columns=("status",),
        ),
        PolicyEvaluationTestCase(
            description="direct source enum column modifier passes",
            model_name="market__stg__prices__vendor",
            relative_path="models/staging/market__stg__prices__vendor.sql",
            sql=(
                'WITH raw_prices AS (SELECT * FROM __source("vendor_prices")), '
                "filtered AS (SELECT status FROM raw_prices "
                "WHERE LOWER(raw_prices.status) = 'win') SELECT status FROM filtered"
            ),
            authored_sql=(
                'WITH raw_prices AS (SELECT * FROM __source("vendor_prices")), '
                "filtered AS (SELECT status FROM raw_prices "
                'WHERE LOWER(raw_prices.status) = @enum("status").WIN) '
                "SELECT status FROM filtered"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD101",),
            expected_codes=(),
            references=(CompileSqlReference(ref_kind="source", ref_name="vendor_prices"),),
            enum_columns=("status",),
        ),
        PolicyEvaluationTestCase(
            description="transitive source enum column modifier faults",
            model_name="market__stg__prices__vendor",
            relative_path="models/staging/market__stg__prices__vendor.sql",
            sql=(
                'WITH raw_prices AS (SELECT * FROM __source("vendor_prices")), '
                "renamed AS (SELECT status FROM raw_prices), "
                "filtered AS (SELECT status FROM renamed "
                "WHERE LOWER(renamed.status) = 'win') SELECT status FROM filtered"
            ),
            authored_sql=(
                'WITH raw_prices AS (SELECT * FROM __source("vendor_prices")), '
                "renamed AS (SELECT status FROM raw_prices), "
                "filtered AS (SELECT status FROM renamed "
                'WHERE LOWER(renamed.status) = @enum("status").WIN) '
                "SELECT status FROM filtered"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD101",),
            expected_codes=("SQBPD101",),
            references=(CompileSqlReference(ref_kind="source", ref_name="vendor_prices"),),
            enum_columns=("status",),
        ),
        PolicyEvaluationTestCase(
            description="modified enum member faults for direct source comparison",
            model_name="market__stg__prices__vendor",
            relative_path="models/staging/market__stg__prices__vendor.sql",
            sql=(
                'WITH raw_prices AS (SELECT * FROM __source("vendor_prices")), '
                "filtered AS (SELECT status FROM raw_prices "
                "WHERE raw_prices.status = LOWER('win')) SELECT status FROM filtered"
            ),
            authored_sql=(
                'WITH raw_prices AS (SELECT * FROM __source("vendor_prices")), '
                "filtered AS (SELECT status FROM raw_prices "
                'WHERE raw_prices.status = LOWER(@enum("status").WIN)) '
                "SELECT status FROM filtered"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD101",),
            expected_codes=("SQBPD101",),
            references=(CompileSqlReference(ref_kind="source", ref_name="vendor_prices"),),
            enum_columns=("status",),
        ),
        PolicyEvaluationTestCase(
            description="bare string faults for direct source comparison",
            model_name="market__stg__prices__vendor",
            relative_path="models/staging/market__stg__prices__vendor.sql",
            sql=(
                'WITH raw_prices AS (SELECT * FROM __source("vendor_prices")), '
                "filtered AS (SELECT status FROM raw_prices "
                "WHERE LOWER(raw_prices.status) = 'win') SELECT status FROM filtered"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD101",),
            expected_codes=("SQBPD101",),
            references=(CompileSqlReference(ref_kind="source", ref_name="vendor_prices"),),
            enum_columns=("status",),
        ),
        PolicyEvaluationTestCase(
            description="numeric decision faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="WITH filtered AS (SELECT id FROM runners WHERE runner_count > 7) SELECT id FROM filtered",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD102",),
            expected_codes=("SQBPD102",),
        ),
        PolicyEvaluationTestCase(
            description="canonical numeric decision passes",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="WITH filtered AS (SELECT id FROM runners WHERE runner_count > 0) SELECT id FROM filtered",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD102",),
            expected_codes=(),
        ),
        PolicyEvaluationTestCase(
            description="numeric decision in projected case faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                "SELECT CASE WHEN runner_count > 7 THEN 'large' ELSE 'small' END AS field_size "
                "FROM runners"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD102",),
            expected_codes=("SQBPD102",),
        ),
        PolicyEvaluationTestCase(
            description="enum decision in projected case faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                "SELECT CASE WHEN status = 'win' THEN 1 ELSE 0 END AS is_win "
                'FROM __ref("market__stg__prices")'
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD101",),
            expected_codes=("SQBPD101",),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
            enum_columns=("status",),
        ),
        PolicyEvaluationTestCase(
            description="constant-backed numeric decision in projected case passes",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                "SELECT CASE WHEN runner_count > 7 THEN 'large' ELSE 'small' END AS field_size "
                "FROM runners"
            ),
            authored_sql=(
                'SELECT CASE WHEN runner_count > @const("large_field") '
                "THEN 'large' ELSE 'small' END AS field_size FROM runners"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD102",),
            expected_codes=(),
        ),
        PolicyEvaluationTestCase(
            description="negative one and one numeric decisions pass",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=("SELECT id FROM runners WHERE previous_rank = -1 OR current_rank = 1"),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD102",),
            expected_codes=(),
        ),
        PolicyEvaluationTestCase(
            description="projected boolean comparison outside case passes",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="SELECT runner_count > 7 AS is_large_field FROM runners",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD102",),
            expected_codes=(),
        ),
        PolicyEvaluationTestCase(
            description="comparison-valued case result is not a decision site",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                "SELECT CASE WHEN enabled THEN runner_count > 7 ELSE FALSE END AS is_large "
                "FROM runners"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPD102",),
            expected_codes=(),
        ),
        PolicyEvaluationTestCase(
            description="view marker mismatch faults",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql="WITH prices AS (SELECT id FROM source_prices) SELECT id FROM prices",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPS103",),
            expected_codes=("SQBPS103",),
        ),
        PolicyEvaluationTestCase(
            description="retired source token faults",
            model_name="sales__stg__orders__legacy_partner",
            relative_path="models/staging/sales__stg__orders__legacy_partner.sql",
            sql="WITH prices AS (SELECT id FROM source_prices) SELECT id FROM prices",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPR103",),
            expected_codes=("SQBPR103",),
            policy_config=PolicyConfig(
                retired_source_tokens={"legacy_partner": "replacement_partner"}
            ),
        ),
        PolicyEvaluationTestCase(
            description="lone star exemption passes",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql="WITH prices AS (SELECT id FROM source_prices) SELECT * FROM prices",
            config_values={"materialized": "view", "contract": "enforced"},
            select=("SQBPS102",),
            expected_codes=(),
            policy_config=PolicyConfig(
                select_star_allow=(
                    SelectStarAllow(
                        paths=("models/mart/*.sql",),
                        reason="Intentional passthrough view",
                    ),
                )
            ),
        ),
        PolicyEvaluationTestCase(
            description="valid dependency import passes",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")), '
                "final AS (SELECT id FROM prices) SELECT id FROM final"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPS101",),
            expected_codes=(),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        PolicyEvaluationTestCase(
            description="transformed dependency import faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                'WITH prices AS (SELECT p.id FROM __ref("market__stg__prices") p '
                "JOIN lookup l ON p.id = l.id), final AS (SELECT id FROM prices) "
                "SELECT id FROM final"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPS101",),
            expected_codes=("SQBPS101",),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        PolicyEvaluationTestCase(
            description="duplicate dependency import faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                'WITH prices_a AS (SELECT * FROM __ref("market__stg__prices")), '
                'prices_b AS (SELECT * FROM __ref("market__stg__prices")), '
                "final AS (SELECT id FROM prices_a) SELECT id FROM final"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBPS101",),
            expected_codes=("SQBPS101",),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        PolicyEvaluationTestCase(
            description="passthrough skips minimum checks",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")) SELECT * FROM prices'
            ),
            config_values={"materialized": "view"},
            select=("SQBPT201", "SQBPT202"),
            expected_codes=(),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        PolicyEvaluationTestCase(
            description="plain column passthrough shares import and exemption classification",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")) '
                "SELECT id, price AS current_price FROM prices"
            ),
            config_values={"materialized": "view"},
            select=("SQBPS101", "SQBPS102", "SQBPT201", "SQBPT202"),
            expected_codes=(),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        PolicyEvaluationTestCase(
            description="join import is neither star-exempt nor passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices") p '
                "JOIN lookup l ON p.id = l.id) SELECT id FROM prices"
            ),
            config_values={"materialized": "view"},
            select=("SQBPS102", "SQBPT201", "SQBPT202"),
            expected_codes=("SQBPS102", "SQBPT201", "SQBPT202"),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        PolicyEvaluationTestCase(
            description="aggregate projection is not passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")) '
                "SELECT COUNT(id) AS price_count FROM prices"
            ),
            config_values={"materialized": "view"},
            select=("SQBPT201", "SQBPT202"),
            expected_codes=("SQBPT201", "SQBPT202"),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        PolicyEvaluationTestCase(
            description="case projection is not passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")) '
                "SELECT CASE WHEN price > 0 THEN id ELSE NULL END AS id FROM prices"
            ),
            config_values={"materialized": "view"},
            select=("SQBPT201", "SQBPT202"),
            expected_codes=("SQBPT201", "SQBPT202"),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        PolicyEvaluationTestCase(
            description="extra logical cte is not passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")), '
                "renamed AS (SELECT id FROM prices) SELECT id FROM renamed"
            ),
            config_values={"materialized": "view"},
            select=("SQBPT201", "SQBPT202"),
            expected_codes=("SQBPT201", "SQBPT202"),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        PolicyEvaluationTestCase(
            description="extra dependency is not passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")), '
                'markets AS (SELECT * FROM __ref("market__stg__markets")) '
                "SELECT id FROM prices"
            ),
            config_values={"materialized": "view"},
            select=("SQBPT201", "SQBPT202"),
            expected_codes=("SQBPT201", "SQBPT202"),
            references=(
                CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),
                CompileSqlReference(ref_kind="ref", ref_name="market__stg__markets"),
            ),
        ),
        PolicyEvaluationTestCase(
            description="derived expression is not passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")) '
                "SELECT price * 100 AS price_cents FROM prices"
            ),
            config_values={"materialized": "view"},
            select=("SQBPT201", "SQBPT202"),
            expected_codes=("SQBPT201", "SQBPT202"),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        PolicyEvaluationTestCase(
            description="nontrivial filter is not passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")) '
                "SELECT id FROM prices WHERE price > 0"
            ),
            config_values={"materialized": "view"},
            select=("SQBPT201", "SQBPT202"),
            expected_codes=("SQBPT201", "SQBPT202"),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        PolicyEvaluationTestCase(
            description="unrelated terminal source is not passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")) '
                "SELECT id FROM unrelated"
            ),
            config_values={"materialized": "view"},
            select=("SQBPT201", "SQBPT202"),
            expected_codes=("SQBPT201", "SQBPT202"),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_selected_rules_when_evaluating_then_reports_expected_faults(
    tmp_path: Path, test_case: PolicyEvaluationTestCase
) -> None:
    result: PolicyResult = evaluate(
        project=build_project(
            name=test_case.model_name,
            relative_path=test_case.relative_path,
            sql=test_case.sql,
            config_values=test_case.config_values,
            references=test_case.references,
            authored_sql=test_case.authored_sql,
            enum_columns=test_case.enum_columns,
        ),
        config=replace(test_case.policy_config, select=test_case.select),
        project_dir=tmp_path,
    )

    assert tuple(sorted(fault.code for fault in result.faults)) == test_case.expected_codes
