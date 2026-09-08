import pytest

from sqlbuild.compiler.contract_adoption._helpers.repository_edits import _declared_type_span
from sqlbuild.compiler.discovery.models import ModelHeaderColumnSpan
from tests.unit.src.sqlbuild.compiler.contract_adoption._helpers._test_types import (
    DeclaredTypeSpanTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DeclaredTypeSpanTestCase(
            description="nested type argument precedes the declared column type",
            contents="amount (audits [custom(type INT)], type INT)",
            declared_type="INT",
            expected_value="INT",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_nested_type_key_when_locating_declared_type_then_returns_top_level_value(
    test_case: DeclaredTypeSpanTestCase,
) -> None:
    contents: str = test_case.contents
    metadata_start: int = contents.index("audits")
    metadata_end: int = contents.rindex(")")
    expected_start: int = contents.rindex(test_case.expected_value)

    result: tuple[int, int] | None = _declared_type_span(
        contents=contents,
        column_span=ModelHeaderColumnSpan(
            entry_start=0,
            entry_end=len(contents),
            metadata_start=metadata_start,
            metadata_end=metadata_end,
        ),
        declared_type=test_case.declared_type,
    )

    assert result == (expected_start, expected_start + len(test_case.expected_value))
