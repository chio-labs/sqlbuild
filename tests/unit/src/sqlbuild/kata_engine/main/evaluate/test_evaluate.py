"""Behavior tests for selected built-in kata rules."""

from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.kata_engine.main.evaluate import evaluate
from sqlbuild.kata_engine.models import (
    KataConfig,
    KataResult,
    RuleExemption,
    RuleIgnore,
    SelectStarAllow,
)
from tests.unit.src.sqlbuild.kata_engine.main.evaluate._test_types import (
    JoinRuleTestCase,
    KataEvaluationTestCase,
)
from tests.unit.src.sqlbuild.kata_engine.main.evaluate.helpers import build_project

COMMA_JOIN_REMEDIATION: str = (
    "Replace the comma-separated source with JOIN ... ON <key> or "
    "JOIN ... USING (<key>) at this FROM."
)
CROSS_JOIN_REMEDIATION: str = (
    "Replace CROSS JOIN with JOIN ... ON <relationship> or JOIN ... USING (<key>); "
    "when the Cartesian product is intentional, add a reasoned exact exception or scoped "
    "ignore through the common policy."
)
JOIN_CONSTRAINT_REMEDIATION: str = (
    "Replace the missing or unconditional constraint with JOIN ... ON <relationship> or "
    "JOIN ... USING (<key>); use CROSS JOIN only when a Cartesian product is intended and "
    "suppressed through the common policy."
)


@pytest.mark.parametrize(
    "test_case",
    (
        KataEvaluationTestCase(
            description="empty selection disables kata",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="SELECT * FROM raw.prices",
            config_values={},
            select=(),
            expected_codes=(),
        ),
        KataEvaluationTestCase(
            description="structure detects missing ctes and output star",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="SELECT * FROM prices",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKS001", "SQBKS201"),
            expected_codes=("SQBKS001", "SQBKS201"),
        ),
        KataEvaluationTestCase(
            description="contract rule faults missing enforced contract",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="WITH prices AS (SELECT id FROM source_prices) SELECT id FROM prices",
            config_values={"materialized": "table"},
            select=("SQBKR401",),
            expected_codes=("SQBKR401",),
        ),
        KataEvaluationTestCase(
            description="meaningless cte and qualified table fault",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="WITH t1 AS (SELECT id FROM raw.prices) SELECT id FROM t1",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKS501", "SQBKL101"),
            expected_codes=("SQBKL101", "SQBKS501"),
        ),
        KataEvaluationTestCase(
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
            select=("SQBKH001",),
            expected_codes=(),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
            enum_columns=("status",),
        ),
        KataEvaluationTestCase(
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
            select=("SQBKH001",),
            expected_codes=("SQBKH001",),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
            enum_columns=("status",),
        ),
        KataEvaluationTestCase(
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
            select=("SQBKH001",),
            expected_codes=("SQBKH001",),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
            enum_columns=("status",),
        ),
        KataEvaluationTestCase(
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
            select=("SQBKH001",),
            expected_codes=("SQBKH001",),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
            enum_columns=("status",),
        ),
        KataEvaluationTestCase(
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
            select=("SQBKH001",),
            expected_codes=(),
            references=(CompileSqlReference(ref_kind="source", ref_name="vendor_prices"),),
            enum_columns=("status",),
        ),
        KataEvaluationTestCase(
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
            select=("SQBKH001",),
            expected_codes=("SQBKH001",),
            references=(CompileSqlReference(ref_kind="source", ref_name="vendor_prices"),),
            enum_columns=("status",),
        ),
        KataEvaluationTestCase(
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
            select=("SQBKH001",),
            expected_codes=("SQBKH001",),
            references=(CompileSqlReference(ref_kind="source", ref_name="vendor_prices"),),
            enum_columns=("status",),
        ),
        KataEvaluationTestCase(
            description="bare string faults for direct source comparison",
            model_name="market__stg__prices__vendor",
            relative_path="models/staging/market__stg__prices__vendor.sql",
            sql=(
                'WITH raw_prices AS (SELECT * FROM __source("vendor_prices")), '
                "filtered AS (SELECT status FROM raw_prices "
                "WHERE LOWER(raw_prices.status) = 'win') SELECT status FROM filtered"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKH001",),
            expected_codes=("SQBKH001",),
            references=(CompileSqlReference(ref_kind="source", ref_name="vendor_prices"),),
            enum_columns=("status",),
        ),
        KataEvaluationTestCase(
            description="numeric decision faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="WITH filtered AS (SELECT id FROM runners WHERE runner_count > 7) SELECT id FROM filtered",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKH002",),
            expected_codes=("SQBKH002",),
        ),
        KataEvaluationTestCase(
            description="canonical numeric decision passes",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="WITH filtered AS (SELECT id FROM runners WHERE runner_count > 0) SELECT id FROM filtered",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKH002",),
            expected_codes=(),
        ),
        KataEvaluationTestCase(
            description="numeric decision in projected case faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                "SELECT CASE WHEN runner_count > 7 THEN 'large' ELSE 'small' END AS field_size "
                "FROM runners"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKH002",),
            expected_codes=("SQBKH002",),
        ),
        KataEvaluationTestCase(
            description="enum decision in projected case faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                "SELECT CASE WHEN status = 'win' THEN 1 ELSE 0 END AS is_win "
                'FROM __ref("market__stg__prices")'
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKH001",),
            expected_codes=("SQBKH001",),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
            enum_columns=("status",),
        ),
        KataEvaluationTestCase(
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
            select=("SQBKH002",),
            expected_codes=(),
        ),
        KataEvaluationTestCase(
            description="negative one and one numeric decisions pass",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=("SELECT id FROM runners WHERE previous_rank = -1 OR current_rank = 1"),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKH002",),
            expected_codes=(),
        ),
        KataEvaluationTestCase(
            description="projected boolean comparison outside case passes",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="SELECT runner_count > 7 AS is_large_field FROM runners",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKH002",),
            expected_codes=(),
        ),
        KataEvaluationTestCase(
            description="comparison-valued case result is not a decision site",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                "SELECT CASE WHEN enabled THEN runner_count > 7 ELSE FALSE END AS is_large "
                "FROM runners"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKH002",),
            expected_codes=(),
        ),
        KataEvaluationTestCase(
            description="view marker mismatch faults",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql="WITH prices AS (SELECT id FROM source_prices) SELECT id FROM prices",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKS401",),
            expected_codes=("SQBKS401",),
        ),
        KataEvaluationTestCase(
            description="retired source token faults",
            model_name="market__stg__prices__centrum_archive",
            relative_path="models/staging/market__stg__prices__centrum_archive.sql",
            sql="WITH prices AS (SELECT id FROM source_prices) SELECT id FROM prices",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKR201",),
            expected_codes=("SQBKR201",),
            kata_config=KataConfig(retired_source_tokens={"centrum_archive": "amtote_archive"}),
        ),
        KataEvaluationTestCase(
            description="lone star exemption passes",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql="WITH prices AS (SELECT id FROM source_prices) SELECT * FROM prices",
            config_values={"materialized": "view", "contract": "enforced"},
            select=("SQBKS201",),
            expected_codes=(),
            kata_config=KataConfig(
                select_star_allow=(
                    SelectStarAllow(
                        paths=("models/mart/*.sql",),
                        reason="Intentional passthrough view",
                    ),
                )
            ),
        ),
        KataEvaluationTestCase(
            description="valid dependency import passes",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")), '
                "final AS (SELECT id FROM prices) SELECT id FROM final"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKS101",),
            expected_codes=(),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        KataEvaluationTestCase(
            description="transformed dependency import faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                'WITH prices AS (SELECT p.id FROM __ref("market__stg__prices") p '
                "JOIN lookup l ON p.id = l.id), final AS (SELECT id FROM prices) "
                "SELECT id FROM final"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKS101",),
            expected_codes=("SQBKS101",),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        KataEvaluationTestCase(
            description="duplicate dependency import faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                'WITH prices_a AS (SELECT * FROM __ref("market__stg__prices")), '
                'prices_b AS (SELECT * FROM __ref("market__stg__prices")), '
                "final AS (SELECT id FROM prices_a) SELECT id FROM final"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKS101",),
            expected_codes=("SQBKS101",),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        KataEvaluationTestCase(
            description="computed terminal select faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="WITH final AS (SELECT 1 AS id) SELECT id + 1 AS id FROM final",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKS002",),
            expected_codes=("SQBKS002",),
        ),
        KataEvaluationTestCase(
            description="positional union star faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                "WITH combined AS (SELECT * FROM prices_a UNION ALL SELECT * FROM prices_b) "
                "SELECT id FROM combined"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKS202",),
            expected_codes=("SQBKS202",),
        ),
        KataEvaluationTestCase(
            description="nested cte faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=(
                "WITH outer_rows AS (WITH inner_rows AS (SELECT 1 AS id) "
                "SELECT id FROM inner_rows) SELECT id FROM outer_rows"
            ),
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKS301",),
            expected_codes=("SQBKS301",),
        ),
        KataEvaluationTestCase(
            description="passthrough skips minimum checks",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")) SELECT * FROM prices'
            ),
            config_values={"materialized": "view"},
            select=("SQBKX001", "SQBKX002"),
            expected_codes=(),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        KataEvaluationTestCase(
            description="plain column passthrough shares import and exemption classification",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")) '
                "SELECT id, price AS current_price FROM prices"
            ),
            config_values={"materialized": "view"},
            select=("SQBKS101", "SQBKS201", "SQBKX001", "SQBKX002"),
            expected_codes=(),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        KataEvaluationTestCase(
            description="join import is neither star-exempt nor passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices") p '
                "JOIN lookup l ON p.id = l.id) SELECT id FROM prices"
            ),
            config_values={"materialized": "view"},
            select=("SQBKS201", "SQBKX001", "SQBKX002"),
            expected_codes=("SQBKS201", "SQBKX001", "SQBKX002"),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        KataEvaluationTestCase(
            description="aggregate projection is not passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")) '
                "SELECT COUNT(id) AS price_count FROM prices"
            ),
            config_values={"materialized": "view"},
            select=("SQBKX001", "SQBKX002"),
            expected_codes=("SQBKX001", "SQBKX002"),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        KataEvaluationTestCase(
            description="case projection is not passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")) '
                "SELECT CASE WHEN price > 0 THEN id ELSE NULL END AS id FROM prices"
            ),
            config_values={"materialized": "view"},
            select=("SQBKX001", "SQBKX002"),
            expected_codes=("SQBKX001", "SQBKX002"),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        KataEvaluationTestCase(
            description="extra logical cte is not passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")), '
                "renamed AS (SELECT id FROM prices) SELECT id FROM renamed"
            ),
            config_values={"materialized": "view"},
            select=("SQBKX001", "SQBKX002"),
            expected_codes=("SQBKX001", "SQBKX002"),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        KataEvaluationTestCase(
            description="extra dependency is not passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")), '
                'markets AS (SELECT * FROM __ref("market__stg__markets")) '
                "SELECT id FROM prices"
            ),
            config_values={"materialized": "view"},
            select=("SQBKX001", "SQBKX002"),
            expected_codes=("SQBKX001", "SQBKX002"),
            references=(
                CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),
                CompileSqlReference(ref_kind="ref", ref_name="market__stg__markets"),
            ),
        ),
        KataEvaluationTestCase(
            description="derived expression is not passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")) '
                "SELECT price * 100 AS price_cents FROM prices"
            ),
            config_values={"materialized": "view"},
            select=("SQBKX001", "SQBKX002"),
            expected_codes=("SQBKX001", "SQBKX002"),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        KataEvaluationTestCase(
            description="nontrivial filter is not passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")) '
                "SELECT id FROM prices WHERE price > 0"
            ),
            config_values={"materialized": "view"},
            select=("SQBKX001", "SQBKX002"),
            expected_codes=("SQBKX001", "SQBKX002"),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
        KataEvaluationTestCase(
            description="unrelated terminal source is not passthrough",
            model_name="market__mart_v__prices",
            relative_path="models/mart/market__mart_v__prices.sql",
            sql=(
                'WITH prices AS (SELECT * FROM __ref("market__stg__prices")) '
                "SELECT id FROM unrelated"
            ),
            config_values={"materialized": "view"},
            select=("SQBKX001", "SQBKX002"),
            expected_codes=("SQBKX001", "SQBKX002"),
            references=(CompileSqlReference(ref_kind="ref", ref_name="market__stg__prices"),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_selected_rules_when_evaluating_then_reports_expected_faults(
    tmp_path: Path, test_case: KataEvaluationTestCase
) -> None:
    result: KataResult = evaluate(
        project=build_project(
            name=test_case.model_name,
            relative_path=test_case.relative_path,
            sql=test_case.sql,
            config_values=test_case.config_values,
            references=test_case.references,
            authored_sql=test_case.authored_sql,
            enum_columns=test_case.enum_columns,
        ),
        config=replace(test_case.kata_config, select=test_case.select),
        project_dir=tmp_path,
    )

    assert tuple(sorted(fault.code for fault in result.faults)) == test_case.expected_codes


@pytest.mark.parametrize(
    "test_case",
    (
        JoinRuleTestCase(
            description="comma join faults with an explicit join remediation",
            sql="WITH joined AS (SELECT a.id FROM a, b) SELECT id FROM joined",
            select=("SQBKJ001",),
            expected_codes=("SQBKJ001",),
            expected_remediations=(COMMA_JOIN_REMEDIATION,),
        ),
        JoinRuleTestCase(
            description="explicit cross join faults with keyed join remediation",
            sql="WITH joined AS (SELECT a.id FROM a CROSS JOIN b) SELECT id FROM joined",
            select=("SQBKJ002",),
            expected_codes=("SQBKJ002",),
            expected_remediations=(CROSS_JOIN_REMEDIATION,),
        ),
        JoinRuleTestCase(
            description="join without a constraint faults",
            sql="WITH joined AS (SELECT a.id FROM a JOIN b) SELECT id FROM joined",
            select=("SQBKJ101",),
            expected_codes=("SQBKJ101",),
            expected_remediations=(JOIN_CONSTRAINT_REMEDIATION,),
        ),
        JoinRuleTestCase(
            description="ON TRUE faults",
            sql="WITH joined AS (SELECT a.id FROM a JOIN b ON TRUE) SELECT id FROM joined",
            select=("SQBKJ101",),
            expected_codes=("SQBKJ101",),
            expected_remediations=(JOIN_CONSTRAINT_REMEDIATION,),
        ),
        JoinRuleTestCase(
            description="equal numeric literals fault regardless of their value",
            sql="WITH joined AS (SELECT a.id FROM a JOIN b ON 0 = 0) SELECT id FROM joined",
            select=("SQBKJ101",),
            expected_codes=("SQBKJ101",),
            expected_remediations=(JOIN_CONSTRAINT_REMEDIATION,),
        ),
        JoinRuleTestCase(
            description="obvious numeric comparison faults",
            sql="WITH joined AS (SELECT a.id FROM a JOIN b ON -1 < 0) SELECT id FROM joined",
            select=("SQBKJ101",),
            expected_codes=("SQBKJ101",),
            expected_remediations=(JOIN_CONSTRAINT_REMEDIATION,),
        ),
        JoinRuleTestCase(
            description="identical decimal literals fault",
            sql="WITH joined AS (SELECT a.id FROM a JOIN b ON 1.0 = 1.0) SELECT id FROM joined",
            select=("SQBKJ101",),
            expected_codes=("SQBKJ101",),
            expected_remediations=(JOIN_CONSTRAINT_REMEDIATION,),
        ),
        JoinRuleTestCase(
            description="unconditional boolean disjunction faults",
            sql=(
                "WITH joined AS (SELECT a.id FROM a JOIN b ON TRUE OR a.id = b.id) "
                "SELECT id FROM joined"
            ),
            select=("SQBKJ101",),
            expected_codes=("SQBKJ101",),
            expected_remediations=(JOIN_CONSTRAINT_REMEDIATION,),
        ),
        JoinRuleTestCase(
            description="equi ON predicate passes",
            sql="WITH joined AS (SELECT a.id FROM a JOIN b ON a.id = b.id) SELECT id FROM joined",
            select=("SQBKJ101",),
            expected_codes=(),
        ),
        JoinRuleTestCase(
            description="USING predicate passes without an ON preference",
            sql="WITH joined AS (SELECT id FROM a JOIN b USING (id)) SELECT id FROM joined",
            select=("SQBKJ101",),
            expected_codes=(),
        ),
        JoinRuleTestCase(
            description="composite predicate passes",
            sql=(
                "WITH joined AS (SELECT a.id FROM a JOIN b "
                "ON a.id = b.id AND a.market_id = b.market_id) SELECT id FROM joined"
            ),
            select=("SQBKJ101",),
            expected_codes=(),
        ),
        JoinRuleTestCase(
            description="non-equi predicate passes",
            sql="WITH joined AS (SELECT a.id FROM a JOIN b ON a.ts < b.ts) SELECT id FROM joined",
            select=("SQBKJ101",),
            expected_codes=(),
        ),
        JoinRuleTestCase(
            description="literal truth combined with a relationship is a near miss",
            sql=(
                "WITH joined AS (SELECT a.id FROM a JOIN b ON 1 = 1 AND a.id = b.id) "
                "SELECT id FROM joined"
            ),
            select=("SQBKJ101",),
            expected_codes=(),
        ),
        JoinRuleTestCase(
            description="column compared with a boolean literal is a near miss",
            sql=(
                "WITH joined AS (SELECT a.id FROM a JOIN b ON a.is_active = TRUE) "
                "SELECT id FROM joined"
            ),
            select=("SQBKJ101",),
            expected_codes=(),
        ),
        JoinRuleTestCase(
            description="statically false predicate is not an unconditional join near miss",
            sql="WITH joined AS (SELECT a.id FROM a JOIN b ON 1 = 0) SELECT id FROM joined",
            select=("SQBKJ101",),
            expected_codes=(),
        ),
        JoinRuleTestCase(
            description="distinct large integers remain a conservative near miss",
            sql=(
                "WITH joined AS (SELECT a.id FROM a JOIN b "
                "ON 9007199254740992 = 9007199254740993) SELECT id FROM joined"
            ),
            select=("SQBKJ101",),
            expected_codes=(),
        ),
        JoinRuleTestCase(
            description="reasoned exact exception suppresses intentional cross join",
            sql="WITH joined AS (SELECT a.id FROM a CROSS JOIN b) SELECT id FROM joined",
            select=("SQBKJ002",),
            expected_codes=(),
            kata_config=KataConfig(
                rule_exceptions=(
                    RuleExemption(
                        rule="SQBKJ002",
                        path="models/mart/market__mart__prices.sql",
                        reason="Intentional small Cartesian matrix",
                    ),
                )
            ),
        ),
        JoinRuleTestCase(
            description="reasoned scoped ignore suppresses intentional cross join",
            sql="WITH joined AS (SELECT a.id FROM a CROSS JOIN b) SELECT id FROM joined",
            select=("SQBKJ002",),
            expected_codes=(),
            kata_config=KataConfig(
                rule_ignores=(
                    RuleIgnore(
                        rules=("SQBKJ002",),
                        paths=("models/mart/**",),
                        reason="Tracked Cartesian migration boundary",
                    ),
                )
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_join_shape_when_evaluating_join_rules_then_enforces_hard_policy(
    tmp_path: Path, test_case: JoinRuleTestCase
) -> None:
    model_path: Path = tmp_path / "models/mart/market__mart__prices.sql"
    model_path.parent.mkdir(parents=True)
    model_path.write_text(test_case.sql, encoding="utf-8")
    result: KataResult = evaluate(
        project=build_project(
            name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql=test_case.sql,
            config_values={"materialized": "table", "contract": "enforced"},
        ),
        config=replace(test_case.kata_config, select=test_case.select),
        project_dir=tmp_path,
    )

    assert tuple(sorted(fault.code for fault in result.faults)) == test_case.expected_codes
    remediations: tuple[str, ...] = tuple(fault.remediation for fault in result.faults)
    assert remediations == test_case.expected_remediations
