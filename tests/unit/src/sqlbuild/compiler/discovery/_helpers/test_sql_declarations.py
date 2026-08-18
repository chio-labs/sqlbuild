from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery._helpers.sql.declarations import (
    parse_constant_declaration_file,
    parse_enum_declaration_file,
)
from sqlbuild.compiler.discovery.exceptions import DeclarationParseError
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    ParseDeclarationFileErrorTestCase,
    ParseDeclarationFileTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ParseDeclarationFileTestCase(
            description="shorthand and explicit enum declarations",
            contents="""
ENUM (
  name market_type,
  members [WIN, PLACE, SHOW],
);

ENUM (
  name source,
  members (
    CENTRUM "centrum",
    PARISTURF "paristurf",
  ),
);
""",
            expected_names=("market_type", "source"),
            expected_scalar_types=("VARCHAR", "VARCHAR"),
            expected_values=(("WIN", "PLACE", "SHOW"), ("centrum", "paristurf")),
        ),
        ParseDeclarationFileTestCase(
            description="integer enum declaration",
            contents="""
ENUM (
  name priority,
  members (LOW 1, HIGH 3),
);
""",
            expected_names=("priority",),
            expected_scalar_types=("INTEGER",),
            expected_values=((1, 3),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_enum_declarations_when_parsing_then_returns_typed_members(
    test_case: ParseDeclarationFileTestCase,
) -> None:
    declarations: tuple[EnumDeclaration, ...] = parse_enum_declaration_file(
        contents=test_case.contents,
        file_path=Path("enums/domain.sql"),
        relative_path=Path("enums/domain.sql"),
    )

    assert tuple(declaration.name for declaration in declarations) == test_case.expected_names
    assert (
        tuple(declaration.scalar_type for declaration in declarations)
        == test_case.expected_scalar_types
    )
    actual_values: list[tuple[str | int, ...]] = []
    for declaration in declarations:
        actual_values.append(tuple(member.value for member in declaration.members))
    assert tuple(actual_values) == test_case.expected_values


@pytest.mark.parametrize(
    "test_case",
    [
        ParseDeclarationFileTestCase(
            description="string and integer constants",
            contents="""
CONSTANT (name min_runners, value 7);
CONSTANT (name fallback_source, value "centrum");
""",
            expected_names=("min_runners", "fallback_source"),
            expected_scalar_types=("INTEGER", "VARCHAR"),
            expected_values=((7,), ("centrum",)),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_constant_declarations_when_parsing_then_returns_typed_values(
    test_case: ParseDeclarationFileTestCase,
) -> None:
    declarations: tuple[ConstantDeclaration, ...] = parse_constant_declaration_file(
        contents=test_case.contents,
        file_path=Path("constants/thresholds.sql"),
        relative_path=Path("constants/thresholds.sql"),
    )

    assert tuple(declaration.name for declaration in declarations) == test_case.expected_names
    assert (
        tuple(declaration.scalar_type for declaration in declarations)
        == test_case.expected_scalar_types
    )
    assert tuple((declaration.value,) for declaration in declarations) == test_case.expected_values


@pytest.mark.parametrize(
    "test_case",
    [
        ParseDeclarationFileErrorTestCase(
            description="mixed enum scalar types",
            contents='ENUM (name state, members (OPEN "open", CLOSED 2));',
            expected_error_fragment="one consistent scalar type",
        ),
        ParseDeclarationFileErrorTestCase(
            description="public private-style name",
            contents="ENUM (name _state, members [OPEN]);",
            expected_error_fragment="must not start with '_'",
        ),
        ParseDeclarationFileErrorTestCase(
            description="numeric shorthand member",
            contents="ENUM (name priority, members [1, 2]);",
            expected_error_fragment="shorthand members must be identifiers",
        ),
        ParseDeclarationFileErrorTestCase(
            description="duplicate declaration key",
            contents="ENUM (name state, name other, members [OPEN]);",
            expected_error_fragment="duplicate key 'name'",
        ),
        ParseDeclarationFileErrorTestCase(
            description="duplicate shorthand member",
            contents="ENUM (name state, members [OPEN, OPEN]);",
            expected_error_fragment="duplicate member 'OPEN'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_enum_declaration_when_parsing_then_raises_declaration_error(
    test_case: ParseDeclarationFileErrorTestCase,
) -> None:
    with pytest.raises(DeclarationParseError, match=test_case.expected_error_fragment):
        parse_enum_declaration_file(
            contents=test_case.contents,
            file_path=Path("enums/domain.sql"),
            relative_path=Path("enums/domain.sql"),
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
