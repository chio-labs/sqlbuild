"""Generated SQL and declaration contexts for the native model loop parity tests."""

from __future__ import annotations

import random
from pathlib import Path

from sqlbuild.compiler.compile.models import (
    DeclarationResolutionContext,
)
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration, EnumMember
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    OwnershipRoot,
    ResourceIdentity,
    VisibilityRecord,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    OwnershipRootKind,
    ResourceKind,
    ScopeKind,
    VisibilityReason,
)
from sqlbuild.sql_values.main.normalize import normalize_sql_value

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
    "quoted_note": ConstantDeclaration(
        "quoted_note",
        normalize_sql_value(raw_value="'" * 600_000, context="test"),
        Path("constants/note.sql"),
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
    inaccessible_enums={
        "staged_status": DeclarationRecord(
            identity=DeclarationIdentity(DeclarationKind.ENUM, "staged_status"),
            path="models/staging/_enums/status.sql",
            line=1,
            column=1,
            scope=ScopeKind.LOCAL,
            ownership_root=OwnershipRoot("models", OwnershipRootKind.RESOURCE, ResourceKind.MODEL),
            owning_path="models/staging",
        )
    },
    inaccessible_constants={
        "staged_cap": DeclarationRecord(
            identity=DeclarationIdentity(DeclarationKind.CONSTANT, "staged_cap"),
            path="models/staging/_constants/cap.sql",
            line=1,
            column=1,
            scope=ScopeKind.INHERITED,
            ownership_root=OwnershipRoot("models", OwnershipRootKind.RESOURCE, ResourceKind.MODEL),
            owning_path="models/staging",
        )
    },
    consumer=_CONSUMER,
)
_WHITESPACE: tuple[str, ...] = ("", " ", "\t", "\n ", "\x1c", "\u00a0", "\u2003")
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
    '@const("_private_cap")',
    '@enum("_private_status").PLACED',
    '@enum("staged_status").PLACED',
    '@const("staged_cap")',
    '@const("quoted_note")',
    '@enum("order_status")',
    "@const(sales_cap)",
    "@enum",
    "@const\u00a0(",
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
    *_INVALID_REFERENCES,
)


def generated_reference_sql(*, rng: random.Random) -> str:
    """Return SQL mixing references, quoted text, comments and Unicode in random order."""

    return _reference_sql(rng=rng, rare_parts=int(rng.random() < 0.15))


def _reference_sql(*, rng: random.Random, rare_parts: int) -> str:
    parts: list[str] = [
        rng.choices((_reference_part, _text_part), weights=(4, 6))[0](rng)
        for _ in range(rng.randint(1, 12))
    ]
    parts.extend(rng.choices(_RARE, k=rare_parts))
    rng.shuffle(parts)
    return "".join(parts)


def _reference_part(rng: random.Random) -> str:
    return rng.choice(_REFERENCES).format(s=rng.choice(_WHITESPACE))


def _text_part(rng: random.Random) -> str:
    return rng.choice(_TEXT)
