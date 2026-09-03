from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.compiler.discovery._helpers.sql.declarations import (
    parse_constant_declaration_file,
    parse_enum_declaration_file,
    parse_model_constant_declarations,
    parse_model_schema_declaration_file,
)
from sqlbuild.compiler.discovery.exceptions import DeclarationParseError
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    EnumDeclaration,
    ModelSchemaDeclaration,
)
from sqlbuild.compiler.resource_names.exceptions import ResourceIdentityError
from sqlbuild.sql_values.models import AuthoredSqlValueCall, SqlValue
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    DeclarationResourceIdentityErrorTestCase,
    ParseDeclarationFileErrorTestCase,
    ParseDeclarationFileTestCase,
    ParseLocalTypedConstantsTestCase,
    ParseModelSchemaDeclarationTestCase,
    ParseTypedConstantsTestCase,
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
    assert (
        tuple((declaration.value.value,) for declaration in declarations)
        == test_case.expected_values
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ParseTypedConstantsTestCase(
            description="all public typed value forms",
            contents="""
CONSTANT (name enabled, value true);
CONSTANT (name ratio, value 0.75);
CONSTANT (name missing_value, value null);
CONSTANT (name usd_rate, type decimal, value "2.4700");
CONSTANT (name countries, value ["GB", "FR", null]);
CONSTANT (name unique_ids, value {2, 1}, render_as array);
CONSTANT (name labels, value (FR "France", GB "Great Britain"));
""",
            expected_kinds=("boolean", "float", "null", "decimal", "list", "set", "object"),
            expected_decimal=Decimal("2.4700"),
            expected_rendering="array",
            expected_object_keys=("FR", "GB"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_typed_public_constants_when_parsing_then_returns_normalized_values(
    test_case: ParseTypedConstantsTestCase,
) -> None:
    declarations: tuple[ConstantDeclaration, ...] = parse_constant_declaration_file(
        contents=test_case.contents,
        file_path=Path("constants/domain.sql"),
        relative_path=Path("constants/domain.sql"),
    )

    assert (
        tuple(declaration.value.kind.value for declaration in declarations)
        == test_case.expected_kinds
    )
    assert declarations[3].value.value == test_case.expected_decimal
    assert declarations[5].render_as is not None
    assert declarations[5].render_as.value == test_case.expected_rendering
    object_entries: tuple[tuple[str, SqlValue], ...] = cast(
        tuple[tuple[str, SqlValue], ...], declarations[6].value.value
    )
    assert tuple(key for key, _ in object_entries) == test_case.expected_object_keys


@pytest.mark.parametrize(
    "test_case",
    [
        ParseLocalTypedConstantsTestCase(
            description="local shorthand and exact decimal wrapper",
            raw_value={
                "_enabled": True,
                "_countries": ["GB", "FR"],
                "_rate": AuthoredSqlValueCall(arguments=(("value", "2.4700"), ("type", "decimal"))),
            },
            expected_kinds=("boolean", "list", "decimal"),
            expected_decimal=Decimal("2.4700"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_local_shorthand_and_wrapper_constants_when_parsing_then_honors_options(
    test_case: ParseLocalTypedConstantsTestCase,
) -> None:
    declarations: tuple[ConstantDeclaration, ...] = parse_model_constant_declarations(
        raw_value=test_case.raw_value,
        model_name="orders",
        relative_path=Path("models/orders.sql"),
    )

    assert (
        tuple(declaration.value.kind.value for declaration in declarations)
        == test_case.expected_kinds
    )
    assert declarations[2].value.value == test_case.expected_decimal


@pytest.mark.parametrize(
    "test_case",
    [
        ParseDeclarationFileErrorTestCase(
            description="missing value",
            contents="CONSTANT (name absent);",
            expected_error_fragment="missing required value",
        ),
        ParseDeclarationFileErrorTestCase(
            description="duplicate set value",
            contents='CONSTANT (name countries, value {"GB", "FR", "GB"});',
            expected_error_fragment="duplicate set value 'GB'",
        ),
        ParseDeclarationFileErrorTestCase(
            description="mixed list types",
            contents='CONSTANT (name countries, value ["GB", 2]);',
            expected_error_fragment=r"constant 'countries'\[1\] has type integer; expected string",
        ),
        ParseDeclarationFileErrorTestCase(
            description="empty list",
            contents="CONSTANT (name countries, value []);",
            expected_error_fragment="list must contain at least one value",
        ),
        ParseDeclarationFileErrorTestCase(
            description="unquoted decimal",
            contents="CONSTANT (name rate, type decimal, value 2.47);",
            expected_error_fragment="requires a quoted decimal string",
        ),
        ParseDeclarationFileErrorTestCase(
            description="scalar render mode",
            contents='CONSTANT (name label, value "GB", render_as array);',
            expected_error_fragment="is string and does not support render_as array",
        ),
        ParseDeclarationFileErrorTestCase(
            description="null type option",
            contents="CONSTANT (name label, value 1, type null);",
            expected_error_fragment="type must be an identifier",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_typed_constant_when_parsing_then_raises_contextual_error(
    test_case: ParseDeclarationFileErrorTestCase,
) -> None:
    with pytest.raises(DeclarationParseError, match=test_case.expected_error_fragment):
        parse_constant_declaration_file(
            contents=test_case.contents,
            file_path=Path("constants/domain.sql"),
            relative_path=Path("constants/domain.sql"),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        ParseDeclarationFileErrorTestCase(
            description="mixed enum scalar types",
            contents='ENUM (name state, members (OPEN "open", CLOSED 2));',
            expected_error_fragment="one consistent scalar type",
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
        ParseDeclarationFileErrorTestCase(
            description="lowercase shorthand member",
            contents="ENUM (name state, members [open]);",
            expected_error_fragment="member identifiers must be uppercase: 'open'",
        ),
        ParseDeclarationFileErrorTestCase(
            description="mixed-case shorthand member",
            contents="ENUM (name state, members [Open]);",
            expected_error_fragment="member identifiers must be uppercase: 'Open'",
        ),
        ParseDeclarationFileErrorTestCase(
            description="lowercase explicit member with lowercase value",
            contents='ENUM (name state, members (open "open"));',
            expected_error_fragment="member identifiers must be uppercase: 'open'",
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


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationResourceIdentityErrorTestCase(
            description="public enum uses private spelling",
            contents="ENUM (name _state, members [OPEN]);",
            expected_error_fragment=(
                "Invalid public enum identity '_state'.*use snake_case 'state'"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_noncanonical_declaration_identity_when_parsing_then_d016_suggests_canonical_identity(
    test_case: DeclarationResourceIdentityErrorTestCase,
) -> None:
    with pytest.raises(
        ResourceIdentityError,
        match=test_case.expected_error_fragment,
    ) as error_info:
        parse_enum_declaration_file(
            contents=test_case.contents,
            file_path=Path("enums/domain.sql"),
            relative_path=Path("enums/domain.sql"),
        )

    assert error_info.value.code == "D016"


@pytest.mark.parametrize(
    "test_case",
    [
        ParseModelSchemaDeclarationTestCase(
            description="base and inherited schema declarations",
            contents="""
SCHEMA (
  name order,
  description "Canonical order",
  columns (
    order_id (type INTEGER, nullable false, audits [not_null]),
    status (type order_status, description "Current status"),
  ),
);
SCHEMA (
  name sourced_order,
  extends order,
  columns (source (type VARCHAR)),
);
""",
            expected_names=("order", "sourced_order"),
            expected_description="Canonical order",
            expected_parent="order",
            expected_base_column_names=("order_id", "status"),
            expected_base_column_line=6,
            expected_child_column_line=13,
            expected_audit_names=("not_null",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_model_schema_declarations_when_parsing_then_returns_typed_columns(
    test_case: ParseModelSchemaDeclarationTestCase,
) -> None:
    declarations: tuple[ModelSchemaDeclaration, ...] = parse_model_schema_declaration_file(
        contents=test_case.contents,
        file_path=Path("schemas/orders.sql"),
        relative_path=Path("schemas/orders.sql"),
    )

    assert tuple(declaration.name for declaration in declarations) == test_case.expected_names
    assert declarations[0].description == test_case.expected_description
    assert declarations[1].extends == test_case.expected_parent
    assert (
        tuple(column.name for column in declarations[0].columns)
        == test_case.expected_base_column_names
    )
    assert declarations[0].columns[0].nullable is False
    assert declarations[0].columns[0].location is not None
    assert declarations[0].columns[0].location.path == Path("schemas/orders.sql")
    assert declarations[0].columns[0].location.line == test_case.expected_base_column_line
    assert declarations[1].columns[0].location is not None
    assert declarations[1].columns[0].location.line == test_case.expected_child_column_line
    assert (
        tuple(audit.definition_name for audit in declarations[0].columns[0].audits)
        == test_case.expected_audit_names
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ParseDeclarationFileErrorTestCase(
            description="empty model schema",
            contents="SCHEMA (name empty, columns ());",
            expected_error_fragment="must declare at least one column",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_empty_model_schema_when_parsing_then_raises_declaration_error(
    test_case: ParseDeclarationFileErrorTestCase,
) -> None:
    with pytest.raises(DeclarationParseError, match=test_case.expected_error_fragment):
        parse_model_schema_declaration_file(
            contents=test_case.contents,
            file_path=Path("schemas/empty.sql"),
            relative_path=Path("schemas/empty.sql"),
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
