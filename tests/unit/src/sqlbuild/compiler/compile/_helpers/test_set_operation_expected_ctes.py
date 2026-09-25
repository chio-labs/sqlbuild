"""Set-operation expected CTEs across every SQL-test kind validate every branch."""

from __future__ import annotations

from itertools import product

import pytest

from sqlbuild.compiler.compile._helpers.sql_tests.core import classify_sql_test_ctes
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlTestCte, CompileSqlTestCtes
from sqlbuild.compiler.compile.types import SqlTestMode
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    SetOperationExpectedKind,
    SetOperationExpectedTestCase,
)

_FILE: str = "tests/unit/orders.sql"
_MISMATCH: str = (
    "SQL test '{file}' must use the same {cte} projection names and order in every "
    "set-operation branch; branch {branch} does not match branch 1"
)
_NOT_SELECT: str = "SQL test '{file}' must define each {cte} set-operation branch as a SELECT query"
_KINDS: tuple[SetOperationExpectedKind, ...] = (
    SetOperationExpectedKind(
        description="model",
        mode=SqlTestMode.MODEL,
        support_ctes=(("__source__raw_orders", "SELECT 1 AS order_id"),),
        expected_cte_name="__expected__orders",
        payload_type="CompileModelSqlTestCtes",
    ),
    SetOperationExpectedKind(
        description="macro",
        mode=SqlTestMode.MACRO,
        support_ctes=(("__macro_actual__", "SELECT 1 AS order_id"),),
        expected_cte_name="__macro_expected__",
        payload_type="CompileDirectLogicSqlTestCtes",
    ),
    SetOperationExpectedKind(
        description="udf",
        mode=SqlTestMode.UDF,
        support_ctes=(("__udf_actual__", "SELECT 1 AS order_id"),),
        expected_cte_name="__udf_expected__",
        payload_type="CompileDirectLogicSqlTestCtes",
    ),
    SetOperationExpectedKind(
        description="table_fn",
        mode=SqlTestMode.TABLE_FN,
        support_ctes=(("__table_fn_actual__", "SELECT 1 AS order_id"),),
        expected_cte_name="__table_fn_expected__",
        payload_type="CompileDirectLogicSqlTestCtes",
    ),
)
_ACCEPTED_SQL: tuple[str, ...] = (
    "SELECT 1 AS order_id INTERSECT SELECT 1 AS order_id",
    "SELECT 1 AS order_id INTERSECT ALL SELECT 1 AS order_id",
    "SELECT 1 AS order_id INTERSECT DISTINCT SELECT 1 AS order_id",
    "SELECT 1 AS order_id EXCEPT SELECT 2 AS order_id",
    "SELECT 1 AS order_id EXCEPT ALL SELECT 2 AS order_id",
    "SELECT 1 AS order_id EXCEPT DISTINCT SELECT 2 AS order_id",
    "SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS order_id",
)
_REJECTED_SQL: tuple[tuple[str, str], ...] = (
    ("SELECT 1 AS order_id INTERSECT SELECT 1 AS other_id", _MISMATCH.replace("{branch}", "2")),
    (
        "SELECT 1 AS order_id EXCEPT ALL SELECT 1 AS order_id, 2 AS extra",
        _MISMATCH.replace("{branch}", "2"),
    ),
    (
        "SELECT 1 AS order_id UNION SELECT 2 AS order_id EXCEPT SELECT 3 AS other_id",
        _MISMATCH.replace("{branch}", "3"),
    ),
    ("SELECT 1 AS order_id EXCEPT VALUES (1)", _NOT_SELECT),
)


@pytest.mark.parametrize(
    "test_case",
    [
        SetOperationExpectedTestCase(
            description=f"{kind.description}: {sql}",
            kind=kind,
            sql=sql,
            expected_payload_type=kind.payload_type,
        )
        for kind, sql in product(_KINDS, _ACCEPTED_SQL)
    ],
    ids=lambda case: case.description,
)
def test_given_set_operation_expected_cte_when_classifying_then_it_is_accepted(
    test_case: SetOperationExpectedTestCase,
) -> None:
    ctes: tuple[CompileSqlTestCte, ...] = (
        *(
            CompileSqlTestCte(name=name, sql_body=body)
            for name, body in test_case.kind.support_ctes
        ),
        CompileSqlTestCte(name=test_case.kind.expected_cte_name, sql_body=test_case.sql),
    )

    classified: CompileSqlTestCtes = classify_sql_test_ctes(
        ctes=ctes, file_label=_FILE, mode=test_case.kind.mode
    )

    assert type(classified.payload).__name__ == test_case.expected_payload_type


@pytest.mark.parametrize(
    "test_case",
    [
        SetOperationExpectedTestCase(
            description=f"{kind.description}: {rejected[0]}",
            kind=kind,
            sql=rejected[0],
            expected_error_template=rejected[1],
        )
        for kind, rejected in product(_KINDS, _REJECTED_SQL)
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_set_operation_branch_when_classifying_then_it_names_the_expected_cte(
    test_case: SetOperationExpectedTestCase,
) -> None:
    ctes: tuple[CompileSqlTestCte, ...] = (
        *(
            CompileSqlTestCte(name=name, sql_body=body)
            for name, body in test_case.kind.support_ctes
        ),
        CompileSqlTestCte(name=test_case.kind.expected_cte_name, sql_body=test_case.sql),
    )

    with pytest.raises(CompileInputError) as error_info:
        _ = classify_sql_test_ctes(ctes=ctes, file_label=_FILE, mode=test_case.kind.mode)

    assert str(error_info.value) == test_case.expected_error_template.format(
        file=_FILE, cte=test_case.kind.expected_cte_name
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
