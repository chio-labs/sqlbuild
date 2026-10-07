"""Generated SQL and declaration contexts for the native model loop parity tests."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile._helpers.render.declarations import (
    expand_declaration_references_result,
    expand_scanned_declaration_references,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    DeclarationExpansionResult,
    DeclarationResolutionContext,
)
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration, EnumMember
from sqlbuild.compiler.model_loop.main._scan_native_declaration_references import (
    scan_native_declaration_references,
)
from sqlbuild.compiler.model_loop.types import NativeDeclarationReference
from sqlbuild.compiler.scopes.models import DeclarationIdentity, ResourceIdentity, VisibilityRecord
from sqlbuild.compiler.scopes.types import DeclarationKind, ResourceKind, VisibilityReason
from sqlbuild.sql_values.main.normalize import normalize_sql_value
from sqlbuild.sql_values.types import CollectionRendering

_CONSUMER: ResourceIdentity = ResourceIdentity(ResourceKind.MODEL, "orders")
_FILE_PATH: Path = Path("models/orders.sql")
_ENUMS: dict[str, EnumDeclaration] = {
    "order_status": EnumDeclaration(
        "order_status",
        (EnumMember("PLACED", "placed"), EnumMember("SHIPPED", 2), EnumMember("NOTED", "it's")),
        "VARCHAR",
        Path("enums/status.sql"),
    ),
}
_CONSTANTS: dict[str, ConstantDeclaration] = {
    "sales_cap": ConstantDeclaration(
        "sales_cap", normalize_sql_value(raw_value=3, context="test"), Path("constants/cap.sql")
    ),
    "label": ConstantDeclaration(
        "label", normalize_sql_value(raw_value="o'k \u00e9", context="test"), Path("c/label.sql")
    ),
    "regions": ConstantDeclaration(
        "regions",
        normalize_sql_value(raw_value=["north", "south"], context="test"),
        Path("constants/regions.sql"),
    ),
}
DECLARATIONS: DeclarationResolutionContext = DeclarationResolutionContext(
    enums=_ENUMS,
    constants=_CONSTANTS,
    enum_visibility={
        "order_status": (
            VisibilityRecord(
                _CONSUMER,
                DeclarationIdentity(DeclarationKind.ENUM, "order_status"),
                VisibilityReason.GLOBAL,
            ),
        )
    },
    constant_visibility={
        name: (
            VisibilityRecord(
                _CONSUMER,
                DeclarationIdentity(DeclarationKind.CONSTANT, name),
                VisibilityReason.GLOBAL,
            ),
        )
        for name in _CONSTANTS
    },
    consumer=_CONSUMER,
)
_WHITESPACE: tuple[str, ...] = ("", " ", "\t", "\n ", "\x1c", "\u00a0")
_REFERENCES: tuple[str, ...] = (
    '@enum({s}"order_status"{s}){s}.{s}PLACED',
    "@enum('order_status').SHIPPED",
    '@enum("order_status").NOTED',
    '@const("sales_cap")',
    "@const({s}'label'{s})",
    '@const("regions")',
)
_INVALID_REFERENCES: tuple[str, ...] = (
    '@enum("order_status").MISSING',
    '@const("unknown_cap")',
    '@enum("order_status")',
    "@const(sales_cap)",
)
_TEXT: tuple[str, ...] = (
    "SELECT ",
    " FROM orders",
    ", ",
    "caf\u00e9 ",
    "\U0001f600 ",
    "@constant ",
    "@enumerate ",
    "price$1 ",
    '$$ @const("sales_cap") $$',
    '$tag$ @enum("x").Y $tag$',
    "'@const(\"sales_cap\")'",
    "'it''s'",
    '"quoted @const(\\"label\\")"',
    "`tick`",
    '-- @const("sales_cap")\n',
    '/* @enum("order_status").PLACED */',
    "@\u00e9 ",
)
_RARE: tuple[str, ...] = (
    "'unterminated ",
    "/* open ",
    "`open ",
    "$q$ open ",
    "@const\u00e9 ",
    *_INVALID_REFERENCES,
)


@dataclass(frozen=True)
class ReferenceParity:
    """Python's expansion (or error text) and the native one (or None) of one SQL string."""

    sql: str
    python: DeclarationExpansionResult | str
    native: DeclarationExpansionResult | None
    native_references: int


def generated_reference_sql(*, rng: random.Random) -> str:
    """Return SQL mixing references, quoted text, comments and Unicode in random order."""

    parts: list[str] = [
        rng.choices((_reference_part, _text_part), weights=(4, 6))[0](rng)
        for _ in range(rng.randint(1, 12))
    ]
    parts.extend(rng.choices(_RARE, k=int(rng.random() < 0.15)))
    rng.shuffle(parts)
    return "".join(parts)


def reference_parities(*, sqls: list[str]) -> list[ReferenceParity]:
    """Expand every string in Python and through the native scan with Python rendering."""

    scanned: tuple[tuple[NativeDeclarationReference, ...] | None, ...] = (
        scan_native_declaration_references(sqls=tuple(sqls))
    )
    return [
        ReferenceParity(
            sql=sql,
            python=_python_outcome(sql=sql),
            native=expand_scanned_declaration_references(
                sql=sql,
                references=references,
                file_path=_FILE_PATH,
                declarations=DECLARATIONS,
                value_renderer=DuckDbAdapter(),
                collection_rendering=CollectionRendering.VALUE_LIST,
            ),
            native_references=len(references or ()),
        )
        for sql, references in zip(sqls, scanned, strict=True)
    ]


def is_native(parity: ReferenceParity) -> bool:
    """Whether the native path expanded the string instead of deferring to Python."""

    return parity.native is not None


def _reference_part(rng: random.Random) -> str:
    return rng.choice(_REFERENCES).format(s=rng.choice(_WHITESPACE))


def _text_part(rng: random.Random) -> str:
    return rng.choice(_TEXT)


def _python_outcome(*, sql: str) -> DeclarationExpansionResult | str:
    try:
        return expand_declaration_references_result(
            sql=sql,
            file_path=_FILE_PATH,
            declarations=DECLARATIONS,
            value_renderer=DuckDbAdapter(),
            collection_rendering=CollectionRendering.VALUE_LIST,
        )
    except CompileInputError as error:
        return str(error)
