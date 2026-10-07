"""Read values out of canonical stage captures without crediting encoded empty collections."""

from __future__ import annotations

import re
from collections.abc import Iterator

from scripts.compiler_differential._helpers.comparing.compare import as_json_object
from scripts.compiler_differential.classes.capture_file import expand_capture_text
from scripts.compiler_differential.constants import (
    CALLABLE_MARKER,
    COLLECTION_CAPTURE_MARKERS,
    TYPE_MARKER,
    UNCANONICAL_CAPTURE_MARKERS,
)

_ENUM_VALUE: re.Pattern[str] = re.compile(r"\.([A-Z_]+)$")


def decoded(value: object) -> object:
    """Unwrap the capture's set and non-string-key mapping encodings into plain lists."""

    encoded: dict[str, object] | None = as_json_object(value)
    if encoded is None or len(encoded) != 1:
        return value
    marker: str = next(iter(encoded))
    return encoded[marker] if marker in COLLECTION_CAPTURE_MARKERS else value


def has_content(value: object) -> bool:
    """Whether a captured value holds anything; encoded empty sets and mappings do not."""

    return bool(decoded(value))


def records(value: object) -> list[dict[str, object]]:
    """Return the objects of a captured list or set."""

    items: object = decoded(value)
    if not isinstance(items, list):
        return []
    return [record for item in items if (record := as_json_object(item)) is not None]


def mapping_records(value: object) -> list[dict[str, object]]:
    """Return the object values of a captured string-keyed mapping, such as macros by name."""

    mapping: dict[str, object] = as_json_object(value) or {}
    return [
        record
        for key, item in mapping.items()
        if key != TYPE_MARKER and (record := as_json_object(item)) is not None
    ]


def mapping_size(value: object) -> int:
    """Return how many entries a captured mapping or list holds."""

    items: object = decoded(value)
    return len(items) if isinstance(items, (dict, list)) else 0


def enum_name(value: object) -> str | None:
    """Return the lower-case member name of a captured enum value."""

    encoded: dict[str, object] | None = as_json_object(value)
    match: re.Match[str] | None = (
        None if encoded is None else _ENUM_VALUE.search(str(encoded.get("__enum__", "")))
    )
    return None if match is None else match.group(1).lower()


def named_values(*, value: object, names: frozenset[str]) -> Iterator[tuple[str, object]]:
    """Yield every `(key, value)` pair below `value` whose key is one of `names`."""

    record: dict[str, object] | None = as_json_object(value)
    children: list[object] = list(value) if isinstance(value, list) else []
    if record is not None:
        yield from ((key, item) for key, item in record.items() if key in names)
        children.extend(record.values())
    for child in children:
        yield from named_values(value=child, names=names)


def capture_problems(
    *, capture_text: str, fields: tuple[str, ...], callable_fields: frozenset[str]
) -> tuple[str, ...]:
    """Return why a capture is incomplete or not canonical; empty when it is sound."""

    capture: dict[str, object] = as_json_object(expand_capture_text(capture_text)) or {}
    problems: list[str] = []
    captured: tuple[str, ...] = tuple(key for key in capture if key != TYPE_MARKER)
    if captured != fields:
        problems.append(f"captured fields {captured} differ from {fields}")
    problems.extend(
        f"capture contains {marker}"
        for marker in UNCANONICAL_CAPTURE_MARKERS
        if f'"{marker}"' in capture_text
    )
    problems.extend(
        f"{field} is not a qualified callable name: {value}"
        for field, value in named_values(value=capture, names=callable_fields)
        if set(as_json_object(value) or {}) != {CALLABLE_MARKER}
    )
    return tuple(problems)
