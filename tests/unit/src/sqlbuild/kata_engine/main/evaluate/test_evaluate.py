"""Behavior tests for selected built-in kata rules."""

from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.kata_engine.main.evaluate import evaluate
from sqlbuild.kata_engine.models import KataConfig, KataResult, SelectStarAllow
from tests.unit.src.sqlbuild.kata_engine.main.evaluate._test_types import KataEvaluationTestCase
from tests.unit.src.sqlbuild.kata_engine.main.evaluate.helpers import build_project


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
            description="comma join faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="WITH joined AS (SELECT a.id FROM a, b) SELECT id FROM joined",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKJ001",),
            expected_codes=("SQBKJ001",),
        ),
        KataEvaluationTestCase(
            description="join without key faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="WITH joined AS (SELECT a.id FROM a JOIN b) SELECT id FROM joined",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKJ101",),
            expected_codes=("SQBKJ101",),
        ),
        KataEvaluationTestCase(
            description="cross join faults",
            model_name="market__mart__prices",
            relative_path="models/mart/market__mart__prices.sql",
            sql="WITH joined AS (SELECT a.id FROM a CROSS JOIN b) SELECT id FROM joined",
            config_values={"materialized": "table", "contract": "enforced"},
            select=("SQBKJ002",),
            expected_codes=("SQBKJ002",),
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
        ),
        config=replace(test_case.kata_config, select=test_case.select),
        project_dir=tmp_path,
    )

    assert tuple(sorted(fault.code for fault in result.faults)) == test_case.expected_codes
