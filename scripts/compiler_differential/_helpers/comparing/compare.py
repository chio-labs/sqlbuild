"""Locate the first difference between two JSON documents."""

from __future__ import annotations

import json
from typing import cast

from scripts.compiler_differential.constants import MISSING_VALUE, VALUE_PREVIEW_CHARACTERS
from scripts.compiler_differential.models import Divergence
from sqlbuild.compiler.frontier.constants import STAGE_CAPTURE_SHARED_MARKER


def first_json_difference(*, left: object, right: object, pointer: str = "") -> Divergence | None:
    """Return the first JSON pointer whose value, type or key order differs."""

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


def shared_digest(value: object) -> str | None:
    """Return the digest a stage-capture `{"__shared__": digest}` reference names."""

    mapping: dict[str, object] | None = as_json_object(value)
    if mapping is None or len(mapping) != 1:
        return None
    digest: object = mapping.get(STAGE_CAPTURE_SHARED_MARKER)
    return digest if isinstance(digest, str) else None


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
            left=preview(list(left)),
            right=preview(list(right)),
        )
    return None


def _divergence(*, location: str, left: object, right: object) -> Divergence:
    return Divergence(location=location, left=preview(left), right=preview(right))


def preview(value: object) -> str:
    """Render a value for a report, shortened to the preview width."""

    rendered: str = (
        value
        if isinstance(value, str) and value == MISSING_VALUE
        else json.dumps(value, ensure_ascii=False)
    )
    if len(rendered) <= VALUE_PREVIEW_CHARACTERS:
        return rendered
    return rendered[: VALUE_PREVIEW_CHARACTERS - 3] + "..."
