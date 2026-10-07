"""Locate the first difference between two JSON documents, texts, or file trees."""

from __future__ import annotations

import json
from typing import cast

from scripts.compiler_differential.constants import MISSING_VALUE, VALUE_PREVIEW_CHARACTERS
from scripts.compiler_differential.models import Divergence


def first_json_difference(*, left: object, right: object, pointer: str = "") -> Divergence | None:
    """Return the first JSON pointer whose value, type, or object key order differs."""

    if type(left) is not type(right):
        return _divergence(location=pointer or "/", left=left, right=right)
    left_object: dict[str, object] | None = as_json_object(left)
    right_object: dict[str, object] | None = as_json_object(right)
    if left_object is not None and right_object is not None:
        return _first_object_difference(left=left_object, right=right_object, pointer=pointer)
    if isinstance(left, list) and isinstance(right, list):
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=False)):
            found: Divergence | None = first_json_difference(
                left=left_item, right=right_item, pointer=f"{pointer}/{index}"
            )
            if found is not None:
                return found
        if len(left) != len(right):
            index: int = min(len(left), len(right))
            return _divergence(
                location=f"{pointer}/{index}",
                left=left[index] if index < len(left) else MISSING_VALUE,
                right=right[index] if index < len(right) else MISSING_VALUE,
            )
        return None
    if left != right:
        return _divergence(location=pointer or "/", left=left, right=right)
    return None


def first_text_difference(*, left: str, right: str) -> Divergence | None:
    """Return the first differing line, numbered from one."""

    if left == right:
        return None
    left_lines: list[str] = left.split("\n")
    right_lines: list[str] = right.split("\n")
    for index in range(max(len(left_lines), len(right_lines))):
        left_line: str = left_lines[index] if index < len(left_lines) else MISSING_VALUE
        right_line: str = right_lines[index] if index < len(right_lines) else MISSING_VALUE
        if left_line != right_line:
            return Divergence(
                location=f"line {index + 1}", left=_preview(left_line), right=_preview(right_line)
            )
    return Divergence(location="end of file", left="<bytes differ>", right="<bytes differ>")


def first_document_difference(*, left: str, right: str) -> Divergence | None:
    """Compare two documents as JSON when both parse, otherwise line by line."""

    try:
        left_payload: object = json.loads(left)
        right_payload: object = json.loads(right)
    except json.JSONDecodeError:
        return first_text_difference(left=left, right=right)
    return first_json_difference(left=left_payload, right=right_payload)


def as_json_object(value: object) -> dict[str, object] | None:
    """Return a decoded JSON object with string keys, or None for any other value."""

    return cast(dict[str, object], value) if isinstance(value, dict) else None


def json_pointer_token(key: str) -> str:
    """Escape one object key as an RFC 6901 reference token."""

    return key.replace("~", "~0").replace("/", "~1")


def _first_object_difference(
    *, left: dict[str, object], right: dict[str, object], pointer: str
) -> Divergence | None:
    for key in (*left, *(key for key in right if key not in left)):
        location: str = f"{pointer}/{json_pointer_token(key)}"
        if key not in left or key not in right:
            return _divergence(
                location=location,
                left=left.get(key, MISSING_VALUE),
                right=right.get(key, MISSING_VALUE),
            )
        found: Divergence | None = first_json_difference(
            left=left[key], right=right[key], pointer=location
        )
        if found is not None:
            return found
    if list(left) != list(right):
        return Divergence(
            location=f"{pointer or '/'} (key order)",
            left=_preview(list(left)),
            right=_preview(list(right)),
        )
    return None


def _divergence(*, location: str, left: object, right: object) -> Divergence:
    return Divergence(location=location, left=_preview(left), right=_preview(right))


def _preview(value: object) -> str:
    rendered: str = (
        value
        if isinstance(value, str) and value == MISSING_VALUE
        else json.dumps(value, ensure_ascii=False)
    )
    if len(rendered) <= VALUE_PREVIEW_CHARACTERS:
        return rendered
    return rendered[: VALUE_PREVIEW_CHARACTERS - 3] + "..."
