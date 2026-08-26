from __future__ import annotations

from decimal import Decimal
from typing import cast

import pytest

from sqlbuild.sql_values._helpers.normalization import sql_value_identity
from sqlbuild.sql_values.exceptions import SqlValueValidationError
from sqlbuild.sql_values.main.normalize import normalize_sql_value
from sqlbuild.sql_values.main.validate_rendered_size import validate_rendered_sql_value_size
from sqlbuild.sql_values.models import AuthoredSqlSet, SqlValue, SqlValueLimits
from tests.unit.src.sqlbuild.sql_values._test_types import (
    NormalizeSqlValueErrorTestCase,
    NormalizeSqlValueTestCase,
    RenderedSqlValueLimitTestCase,
    SqlValueBehaviorTestCase,
    SqlValueLimitTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        NormalizeSqlValueTestCase("string", "GB", "string", "GB"),
        NormalizeSqlValueTestCase("integer", 7, "integer", 7),
        NormalizeSqlValueTestCase("boolean", True, "boolean", True),
        NormalizeSqlValueTestCase("float", 0.75, "float", 0.75),
        NormalizeSqlValueTestCase(
            "native decimal", Decimal("2.4700"), "decimal", Decimal("2.4700")
        ),
        NormalizeSqlValueTestCase("null", None, "null", None),
        NormalizeSqlValueTestCase(
            "quoted exact decimal", "2.4700", "decimal", Decimal("2.4700"), explicit_type="decimal"
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_supported_scalar_when_normalizing_then_preserves_typed_value(
    test_case: NormalizeSqlValueTestCase,
) -> None:
    value: SqlValue = normalize_sql_value(
        raw_value=test_case.raw_value,
        explicit_type=test_case.explicit_type,
        context="constant 'usd_rate'",
    )

    assert value.kind.value == test_case.expected_kind
    assert value.value == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        SqlValueBehaviorTestCase(
            description="canonical collections and objects",
            expected_list_values=(2, 1, 2),
            expected_identities_equal=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_lists_sets_and_objects_when_normalizing_then_canonicalizes_unordered_values(
    test_case: SqlValueBehaviorTestCase,
) -> None:
    list_value: SqlValue = normalize_sql_value(raw_value=[2, 1, 2], context="constant 'ordered'")
    first_set: SqlValue = normalize_sql_value(
        raw_value=AuthoredSqlSet((2, 1)), context="constant 'unique'"
    )
    second_set: SqlValue = normalize_sql_value(
        raw_value=AuthoredSqlSet((1, 2)), context="constant 'unique'"
    )
    first_object: SqlValue = normalize_sql_value(
        raw_value={"z": 1, "a": [True, None]}, context="constant 'rules'"
    )
    second_object: SqlValue = normalize_sql_value(
        raw_value={"a": [True, None], "z": 1}, context="constant 'rules'"
    )

    list_items: tuple[SqlValue, ...] = cast(tuple[SqlValue, ...], list_value.value)
    assert tuple(item.value for item in list_items) == test_case.expected_list_values
    assert (
        sql_value_identity(value=first_set) == sql_value_identity(value=second_set)
    ) is test_case.expected_identities_equal
    assert (
        sql_value_identity(value=first_object) == sql_value_identity(value=second_object)
    ) is test_case.expected_identities_equal


@pytest.mark.parametrize(
    "test_case",
    [
        NormalizeSqlValueErrorTestCase("empty list", [], "list must contain at least one value"),
        NormalizeSqlValueErrorTestCase(
            "all-null list", [None, None], "cannot infer an element type"
        ),
        NormalizeSqlValueErrorTestCase(
            "mixed list", ["GB", 1], r"\[1\] has type integer; expected string"
        ),
        NormalizeSqlValueErrorTestCase(
            "duplicate set", AuthoredSqlSet(("GB", "GB")), "duplicate set value 'GB'"
        ),
        NormalizeSqlValueErrorTestCase("large integer", 2**63, "outside the signed 64-bit range"),
        NormalizeSqlValueErrorTestCase("infinite float", float("inf"), "float must be finite"),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_values_when_normalizing_then_raises_contextual_error(
    test_case: NormalizeSqlValueErrorTestCase,
) -> None:
    with pytest.raises(
        SqlValueValidationError,
        match=rf"constant 'countries'.*{test_case.expected_error}",
    ):
        normalize_sql_value(raw_value=test_case.raw_value, context="constant 'countries'")


@pytest.mark.parametrize(
    "test_case",
    [SqlValueBehaviorTestCase(description="boolean and integer identities remain distinct")],
    ids=lambda case: case.description,
)
def test_given_python_equal_cross_type_values_when_identifying_then_identity_remains_typed(
    test_case: SqlValueBehaviorTestCase,
) -> None:
    boolean: SqlValue = normalize_sql_value(raw_value=True, context="constant 'value'")
    integer: SqlValue = normalize_sql_value(raw_value=1, context="constant 'value'")

    assert (
        sql_value_identity(value=boolean) == sql_value_identity(value=integer)
    ) is test_case.expected_identities_equal


@pytest.mark.parametrize(
    "test_case",
    [
        SqlValueLimitTestCase(
            "depth", [[[1]]], SqlValueLimits(max_depth=2), "maximum nesting depth"
        ),
        SqlValueLimitTestCase(
            "elements", [1, 2], SqlValueLimits(max_elements=1), "maximum element count"
        ),
        SqlValueLimitTestCase(
            "size", "oversized", SqlValueLimits(max_size=3), "maximum value size"
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_safety_limit_is_exceeded_when_normalizing_then_rejects_value(
    test_case: SqlValueLimitTestCase,
) -> None:
    with pytest.raises(SqlValueValidationError, match=test_case.expected_error):
        normalize_sql_value(
            raw_value=test_case.raw_value,
            context="constant 'limited'",
            limits=test_case.limits,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        RenderedSqlValueLimitTestCase(
            description="multibyte rendered SQL uses UTF-8 byte length",
            rendered_sql="é",
            max_size=1,
            expected_size=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rendered_sql_exceeds_limit_when_validating_then_counts_utf8_bytes(
    test_case: RenderedSqlValueLimitTestCase,
) -> None:
    with pytest.raises(
        SqlValueValidationError,
        match=rf"rendered value is {test_case.expected_size} bytes",
    ):
        validate_rendered_sql_value_size(
            rendered_sql=test_case.rendered_sql,
            context="constant 'limited'",
            max_size=test_case.max_size,
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
