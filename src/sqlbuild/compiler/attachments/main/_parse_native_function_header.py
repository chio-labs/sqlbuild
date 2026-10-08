"""Parse a SQL or Python function header natively for the preview compiler engine."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.attachments.models import NativeFunctionHeader, NativeNamedType


def parse_native_function_header(
    *, header_values: dict[str, object], python: bool
) -> NativeFunctionHeader | None:
    """Return the parsed header, or None where Python must parse it and raise its errors."""

    if not isinstance(header_values, dict):
        return None
    row: (
        tuple[
            list[tuple[str, str, str]],
            str | None,
            list[tuple[str, str, str]] | None,
            list[str],
            str | None,
            str | None,
            str | None,
            list[str],
        ]
        | None
    ) = _native.parse_function_header_values(header_values, python)
    if row is None:
        return None
    arguments, returns, columns, tags, description, runtime_version, entry_point, packages = row
    return NativeFunctionHeader(
        arguments=_named_types(arguments),
        returns=returns,
        return_columns=None if columns is None else _named_types(columns),
        tags=tuple(tags),
        description=description,
        runtime_version=runtime_version,
        entry_point=entry_point,
        packages=tuple(packages),
    )


def _named_types(rows: list[tuple[str, str, str]]) -> tuple[NativeNamedType, ...]:
    return tuple(NativeNamedType(*row) for row in rows)
