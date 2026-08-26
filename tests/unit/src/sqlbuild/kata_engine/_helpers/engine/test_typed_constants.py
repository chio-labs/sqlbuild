from decimal import Decimal
from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.models import ConstantDeclaration
from sqlbuild.kata_engine._helpers.engine.native import (
    _constant_payload,  # noqa: FFL102 - verifies the native protocol payload boundary
)
from sqlbuild.sql_values.main.normalize import normalize_sql_value
from tests.unit.src.sqlbuild.kata_engine._helpers.engine._test_types import (
    TypedConstantPayloadTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        TypedConstantPayloadTestCase(
            description="nested typed value is JSON-safe and type-bearing",
            raw_value={"rate": Decimal("2.4700"), "countries": ["GB", "FR"]},
            expected_value={"countries": ["GB", "FR"], "rate": "2.4700"},
            expected_type="object",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_typed_constant_when_building_native_payload_then_value_and_type_are_preserved(
    test_case: TypedConstantPayloadTestCase,
) -> None:
    declaration: ConstantDeclaration = ConstantDeclaration(
        name="rules",
        value=normalize_sql_value(raw_value=test_case.raw_value, context="constant 'rules'"),
        relative_path=Path("constants/rules.sql"),
    )

    payload: dict[str, object] = _constant_payload(declaration)

    assert payload["value"] == test_case.expected_value
    assert payload["value_type"] == test_case.expected_type
    assert payload["render_as"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
