"""Characterisation tests for macro, UDF, and table_fn SQL-test CTE classification errors."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.sql_tests.core import classify_sql_test_ctes
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlTestCte
from sqlbuild.compiler.compile.types import SqlTestMode
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    ClassifyDirectLogicSqlTestCtesErrorTestCase,
)

_FILE: str = "tests/unit/orders.sql"


@pytest.mark.parametrize(
    "test_case",
    [
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="macro duplicate actual",
            mode=SqlTestMode.MACRO,
            ctes=(("__macro_actual__", "SELECT 1"), ("__macro_actual__", "SELECT 2")),
            expected_message=(
                f"SQL test '{_FILE}' mode 'macro' must define exactly one __macro_actual__ CTE"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="macro duplicate expected",
            mode=SqlTestMode.MACRO,
            ctes=(
                ("__macro_expected__", "SELECT 1 AS value"),
                ("__macro_expected__", "SELECT 2 AS value"),
            ),
            expected_message=(
                f"SQL test '{_FILE}' mode 'macro' must define exactly one __macro_expected__ CTE"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="macro model-test cte",
            mode=SqlTestMode.MACRO,
            ctes=(("__ref__orders", "SELECT 1"),),
            expected_message=(
                f"SQL test '{_FILE}' is mode 'macro' but defines model-test CTE '__ref__orders'"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="macro udf-test cte",
            mode=SqlTestMode.MACRO,
            ctes=(("__udf_actual__", "SELECT 1"),),
            expected_message=(
                f"SQL test '{_FILE}' is mode 'macro' but defines UDF-test CTE '__udf_actual__'"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="macro table_fn-test cte",
            mode=SqlTestMode.MACRO,
            ctes=(("__table_fn_expected__", "SELECT 1 AS value"),),
            expected_message=(
                f"SQL test '{_FILE}' is mode 'macro' but defines table_fn-test CTE "
                "'__table_fn_expected__'"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="macro reserved helper name",
            mode=SqlTestMode.MACRO,
            ctes=(("__missing__", "SELECT 1"),),
            expected_message=f"SQL test '{_FILE}' uses reserved helper CTE name '__missing__'",
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="macro missing expected",
            mode=SqlTestMode.MACRO,
            ctes=(("__macro_actual__", "SELECT 1"),),
            expected_message=(
                f"SQL test '{_FILE}' mode 'macro' must define exactly one __macro_actual__ CTE "
                "and exactly one __macro_expected__ CTE"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="macro helper calls macro",
            mode=SqlTestMode.MACRO,
            ctes=(
                ("helper", "SELECT @normalize_status('paid') AS status"),
                ("__macro_actual__", "SELECT 1 AS status"),
                ("__macro_expected__", "SELECT 1 AS status"),
            ),
            expected_message=(
                f"SQL test '{_FILE}' mode 'macro' helper CTE 'helper' must not call macros; "
                "call macros only in __macro_actual__"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="macro expected calls macro",
            mode=SqlTestMode.MACRO,
            ctes=(
                ("__macro_actual__", "SELECT 1 AS status"),
                ("__macro_expected__", "SELECT @normalize_status('paid') AS status"),
            ),
            expected_message=(
                f"SQL test '{_FILE}' mode 'macro' CTE __macro_expected__ must not call macros"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="macro expected unaliased projection names the expected cte",
            mode=SqlTestMode.MACRO,
            ctes=(
                ("__macro_actual__", "SELECT 1 AS status"),
                ("__macro_expected__", "SELECT 1 + 1"),
            ),
            expected_message=(
                f"SQL test '{_FILE}' must alias every non-trivial __macro_expected__ projection"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="table_fn expected branch mismatch names the expected cte",
            mode=SqlTestMode.TABLE_FN,
            ctes=(
                ("__table_fn_actual__", "SELECT 1 AS value"),
                ("__table_fn_expected__", "SELECT 1 AS value UNION ALL SELECT 2 AS other"),
            ),
            expected_message=(
                f"SQL test '{_FILE}' must use the same __table_fn_expected__ projection names "
                "and order in every set-operation branch; branch 2 does not match branch 1"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="udf duplicate actual",
            mode=SqlTestMode.UDF,
            ctes=(("__udf_actual__", "SELECT 1"), ("__udf_actual__", "SELECT 2")),
            expected_message=(
                f"SQL test '{_FILE}' mode 'udf' must define exactly one __udf_actual__ CTE"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="udf duplicate expected",
            mode=SqlTestMode.UDF,
            ctes=(
                ("__udf_expected__", "SELECT 1 AS value"),
                ("__udf_expected__", "SELECT 2 AS value"),
            ),
            expected_message=(
                f"SQL test '{_FILE}' mode 'udf' must define exactly one __udf_expected__ CTE"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="udf model-test cte",
            mode=SqlTestMode.UDF,
            ctes=(("__expected__orders", "SELECT 1"),),
            expected_message=(
                f"SQL test '{_FILE}' is mode 'udf' but defines model-test CTE '__expected__orders'"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="udf macro-test cte",
            mode=SqlTestMode.UDF,
            ctes=(("__macro_expected__", "SELECT 1 AS value"),),
            expected_message=(
                f"SQL test '{_FILE}' is mode 'udf' but defines macro-test CTE '__macro_expected__'"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="udf table_fn-test cte",
            mode=SqlTestMode.UDF,
            ctes=(("__table_fn_actual__", "SELECT 1"),),
            expected_message=(
                f"SQL test '{_FILE}' is mode 'udf' but defines table_fn-test CTE "
                "'__table_fn_actual__'"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="udf reserved helper name",
            mode=SqlTestMode.UDF,
            ctes=(("__actual", "SELECT 1"),),
            expected_message=f"SQL test '{_FILE}' uses reserved helper CTE name '__actual'",
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="udf missing actual",
            mode=SqlTestMode.UDF,
            ctes=(("__udf_expected__", "SELECT 1 AS value"),),
            expected_message=(
                f"SQL test '{_FILE}' mode 'udf' must define exactly one __udf_actual__ CTE "
                "and exactly one __udf_expected__ CTE"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="udf helper calls macro",
            mode=SqlTestMode.UDF,
            ctes=(
                ("helper", "SELECT @normalize_status('paid') AS status"),
                ("__udf_actual__", "SELECT 1 AS formatted"),
                ("__udf_expected__", "SELECT 1 AS formatted"),
            ),
            expected_message=(
                f"SQL test '{_FILE}' mode 'udf' helper CTE 'helper' must not call macros"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="udf expected calls udf",
            mode=SqlTestMode.UDF,
            ctes=(
                ("__udf_actual__", "SELECT 1 AS formatted"),
                ("__udf_expected__", 'SELECT __udf("format_cents")(1250) AS formatted'),
            ),
            expected_message=(
                f"SQL test '{_FILE}' mode 'udf' CTE __udf_expected__ must not call udf; "
                "call reusable logic only in __udf_actual__"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="table_fn duplicate actual",
            mode=SqlTestMode.TABLE_FN,
            ctes=(("__table_fn_actual__", "SELECT 1"), ("__table_fn_actual__", "SELECT 2")),
            expected_message=(
                f"SQL test '{_FILE}' mode 'table_fn' must define exactly one "
                "__table_fn_actual__ CTE"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="table_fn duplicate expected",
            mode=SqlTestMode.TABLE_FN,
            ctes=(
                ("__table_fn_expected__", "SELECT 1 AS value"),
                ("__table_fn_expected__", "SELECT 2 AS value"),
            ),
            expected_message=(
                f"SQL test '{_FILE}' mode 'table_fn' must define exactly one "
                "__table_fn_expected__ CTE"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="table_fn model-test cte",
            mode=SqlTestMode.TABLE_FN,
            ctes=(("__source__raw_orders", "SELECT 1"),),
            expected_message=(
                f"SQL test '{_FILE}' is mode 'table_fn' but defines model-test CTE "
                "'__source__raw_orders'"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="table_fn macro cte uses generic direct-logic wording",
            mode=SqlTestMode.TABLE_FN,
            ctes=(("__macro_actual__", "SELECT 1"),),
            expected_message=(
                f"SQL test '{_FILE}' is mode 'table_fn' but defines another direct-logic CTE "
                "'__macro_actual__'"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="table_fn udf cte uses generic direct-logic wording",
            mode=SqlTestMode.TABLE_FN,
            ctes=(("__udf_expected__", "SELECT 1 AS value"),),
            expected_message=(
                f"SQL test '{_FILE}' is mode 'table_fn' but defines another direct-logic CTE "
                "'__udf_expected__'"
            ),
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="table_fn reserved helper name",
            mode=SqlTestMode.TABLE_FN,
            ctes=(("__unexpected__", "SELECT 1"),),
            expected_message=f"SQL test '{_FILE}' uses reserved helper CTE name '__unexpected__'",
        ),
        ClassifyDirectLogicSqlTestCtesErrorTestCase(
            description="table_fn missing both",
            mode=SqlTestMode.TABLE_FN,
            ctes=(("helper", "SELECT 1"),),
            expected_message=(
                f"SQL test '{_FILE}' mode 'table_fn' must define exactly one "
                "__table_fn_actual__ CTE and exactly one __table_fn_expected__ CTE"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_direct_logic_ctes_when_classifying_then_raises_mode_specific_message(
    test_case: ClassifyDirectLogicSqlTestCtesErrorTestCase,
) -> None:
    ctes: tuple[CompileSqlTestCte, ...] = tuple(
        CompileSqlTestCte(name=name, sql_body=body) for name, body in test_case.ctes
    )

    with pytest.raises(CompileInputError) as error_info:
        _ = classify_sql_test_ctes(ctes=ctes, file_label=_FILE, mode=test_case.mode)

    assert str(error_info.value) == test_case.expected_message
