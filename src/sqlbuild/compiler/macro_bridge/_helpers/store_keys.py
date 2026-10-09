"""Value-based text of everything a stored macro call result depends on besides its call text."""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import enum
import json
import types
from pathlib import PurePath

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import (
    DeclarationResolutionContext,
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.macro_bridge.constants import VALUE_RENDERER_FIELD
from sqlbuild.compiler.macro_bridge.exceptions import UncacheableValueError
from sqlbuild.compiler.scopes.models import DeclarationIdentity
from sqlbuild.python_nodes.models import SqlResourceRef

_UNSTABLE_KEY_ERRORS: tuple[type[Exception], ...] = (
    UncacheableValueError,
    UnicodeEncodeError,
    RecursionError,
)


def macro_store_token(*, loaded: LoadedMacro, identity: DeclarationIdentity | None) -> str | None:
    """Name a macro by its name, file, identity and exact source, or None when it has no key."""

    try:
        return _encodable(
            _key_text(
                [
                    loaded.name,
                    loaded.relative_path.as_posix(),
                    _canonical(identity),
                    _native.content_digest([loaded.raw_source]),
                ]
            )
        )
    except _UNSTABLE_KEY_ERRORS:
        return None


def context_store_token(
    *, macro_context: MacroContext, declarations: DeclarationResolutionContext | None
) -> str | None:
    """Digest the whole context a macro may read, or None when a value has no stable text."""

    try:
        return _native.content_digest(
            [
                _key_text(
                    [
                        _canonical_context(macro_context),
                        None
                        if declarations is None
                        else [
                            _canonical(declarations.constants),
                            _canonical(declarations.enums),
                            sorted(declarations.inaccessible_constants),
                            sorted(declarations.inaccessible_enums),
                        ],
                    ]
                )
            ]
        )
    except _UNSTABLE_KEY_ERRORS:
        return None


def call_class_store_text(
    *,
    macro_tokens: tuple[str, ...],
    context_token: str | None,
    prior_relations: tuple[SqlResourceRef, ...] | None,
) -> str | None:
    """Text of one persistent call class, or None when a relation name has no UTF-8 text."""

    try:
        return _encodable(
            _key_text(
                [
                    list(macro_tokens),
                    context_token,
                    None
                    if prior_relations is None
                    else [[relation.kind.value, relation.name] for relation in prior_relations],
                ]
            )
        )
    except UnicodeEncodeError:
        return None


def _canonical_context(macro_context: MacroContext) -> object:
    fields: list[object] = []
    for field in dataclasses.fields(macro_context):
        value: object = getattr(macro_context, field.name)
        fields.append(
            [
                field.name,
                _type_name(type(value))
                if field.name == VALUE_RENDERER_FIELD
                else _canonical(value),
            ]
        )
    return [_type_name(type(macro_context)), fields]


def _canonical(value: object) -> object:  # noqa: PLR0911
    if isinstance(value, enum.Enum):
        return ["enum", _type_name(type(value)), _canonical(value.value)]
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return ["int", str(value)]
    if isinstance(value, float):
        return ["float", value.hex()]
    if isinstance(value, decimal.Decimal):
        return ["decimal", str(value)]
    if isinstance(value, datetime.date | datetime.time):
        return [_type_name(type(value)), value.isoformat()]
    if isinstance(value, datetime.timedelta):
        return ["timedelta", value.days, value.seconds, value.microseconds]
    if isinstance(value, bytes):
        return ["bytes", value.hex()]
    if isinstance(value, PurePath):
        return ["path", value.as_posix()]
    if isinstance(value, list | tuple):
        return [_type_name(type(value)), [_canonical(item) for item in value]]
    if isinstance(value, set | frozenset):
        return [
            _type_name(type(value)),
            sorted(json.dumps(_canonical(item), sort_keys=True) for item in value),
        ]
    if isinstance(value, dict | types.MappingProxyType):
        return [
            "mapping",
            [[_canonical(key), _canonical(item)] for key, item in value.items()],
        ]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return [
            _type_name(type(value)),
            [
                [field.name, _canonical(getattr(value, field.name))]
                for field in dataclasses.fields(value)
            ],
        ]
    raise UncacheableValueError(_type_name(type(value)))


def _type_name(kind: type) -> str:
    return f"{kind.__module__}.{kind.__qualname__}"


def _key_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _encodable(text: str) -> str:
    """Return `text`, raising `UnicodeEncodeError` when the native store cannot hold it."""

    _ = text.encode("utf-8")
    return text
