"""Locate the first difference between two JSON documents, texts, or file trees."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import cast

from scripts.compiler_differential.constants import MISSING_VALUE, VALUE_PREVIEW_CHARACTERS
from scripts.compiler_differential.models import Divergence
from scripts.compiler_differential.types import NodeResolvers
from sqlbuild.compiler.frontier.constants import STAGE_CAPTURE_SHARED_MARKER


def first_json_difference(
    *,
    left: object,
    right: object,
    pointer: str = "",
    resolve: NodeResolvers | None = None,
    ignored: frozenset[str] = frozenset(),
) -> Divergence | None:
    """Return the first JSON pointer outside `ignored` whose value, type or key order differs."""

    if resolve is not None:
        left_digest: str | None = shared_digest(left)
        if left_digest is not None and left_digest == shared_digest(right):
            return None
        left, right = resolve[0](left), resolve[1](right)
    if type(left) is not type(right):
        return _divergence(location=pointer or "/", left=left, right=right)
    left_object: dict[str, object] | None = as_json_object(left)
    right_object: dict[str, object] | None = as_json_object(right)
    if left_object is not None and right_object is not None:
        return _first_object_difference(
            left=left_object, right=right_object, pointer=pointer, resolve=resolve, ignored=ignored
        )
    if isinstance(left, list) and isinstance(right, list):
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=False)):
            found: Divergence | None = first_json_difference(
                left=left_item,
                right=right_item,
                pointer=f"{pointer}/{index}",
                resolve=resolve,
                ignored=ignored,
            )
            if found is not None:
                return found
        if len(left) != len(right):
            index: int = min(len(left), len(right))
            return _divergence(
                location=f"{pointer}/{index}",
                left=_shown(value=left[index], resolve=resolve, side=0)
                if index < len(left)
                else MISSING_VALUE,
                right=_shown(value=right[index], resolve=resolve, side=1)
                if index < len(right)
                else MISSING_VALUE,
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
                location=f"line {index + 1}", left=preview(left_line), right=preview(right_line)
            )
    return Divergence(location="end of file", left="<bytes differ>", right="<bytes differ>")


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
    *,
    left: dict[str, object],
    right: dict[str, object],
    pointer: str,
    resolve: NodeResolvers | None,
    ignored: frozenset[str],
) -> Divergence | None:
    for key in (*left, *(key for key in right if key not in left)):
        location: str = f"{pointer}/{json_pointer_token(key)}"
        if location in ignored:
            continue
        if key not in left or key not in right:
            return _divergence(
                location=location,
                left=_shown(value=left.get(key, MISSING_VALUE), resolve=resolve, side=0),
                right=_shown(value=right.get(key, MISSING_VALUE), resolve=resolve, side=1),
            )
        found: Divergence | None = first_json_difference(
            left=left[key], right=right[key], pointer=location, resolve=resolve, ignored=ignored
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


def _shown(*, value: object, resolve: NodeResolvers | None, side: int) -> object:
    if resolve is None:
        return value
    return _previewed(value=value, resolve=resolve[side], remaining=VALUE_PREVIEW_CHARACTERS)[0]


def _previewed(
    *, value: object, resolve: Callable[[object], object], remaining: int
) -> tuple[object, int]:
    if remaining <= 0:
        return value, remaining
    resolved: object = resolve(value)
    mapping: dict[str, object] | None = as_json_object(resolved)
    if mapping is not None:
        shown: dict[str, object] = {}
        for key, item in mapping.items():
            shown[key], remaining = _previewed(
                value=item, resolve=resolve, remaining=remaining - len(key)
            )
        return shown, remaining
    if isinstance(resolved, list):
        items: list[object] = []
        for item in resolved:
            shown_item, remaining = _previewed(value=item, resolve=resolve, remaining=remaining)
            items.append(shown_item)
        return items, remaining
    return resolved, remaining - len(json.dumps(resolved, ensure_ascii=False))


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
