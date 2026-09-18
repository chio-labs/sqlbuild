"""Bounded, diff-aware rendering for row-diff evidence."""

from __future__ import annotations

import hashlib

from sqlbuild.cli.commands.models import DiffExampleRenderOptions, RenderedDiffExampleValue

_MAX_RENDERED_KEY_LENGTH: int = 256


def render_example_pair(
    *,
    left_value: object,
    right_value: object,
    options: DiffExampleRenderOptions,
) -> tuple[RenderedDiffExampleValue, RenderedDiffExampleValue]:
    """Render two unequal values around their first differing character."""

    left_text: str = str(left_value)
    right_text: str = str(right_value)
    first_difference: int | None = _first_difference(left=left_text, right=right_text)
    return (
        _render_value(text=left_text, first_difference=first_difference, options=options),
        _render_value(text=right_text, first_difference=first_difference, options=options),
    )


def display_example_value(value: RenderedDiffExampleValue) -> str:
    """Render one bounded value for terminal output."""

    if value.suppressed:
        return f"<value suppressed; {value.original_length:,} chars>"
    rendered: str = value.text or ""
    if value.truncated:
        return f"{rendered} [truncated; {value.original_length:,} chars]"
    return rendered


def render_key_value(value: object) -> str:
    """Keep ordinary keys complete and identify exceptionally long shortened keys."""

    text: str = str(value)
    if len(text) <= _MAX_RENDERED_KEY_LENGTH:
        return text
    digest: str = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{text[:_MAX_RENDERED_KEY_LENGTH]}… [truncated; {len(text):,} chars; sha256:{digest}]"


def example_value_payload(value: RenderedDiffExampleValue) -> dict[str, object]:
    """Build stable structured evidence for one rendered value."""

    return {
        "value": value.text,
        "original_length": value.original_length,
        "truncated": value.truncated,
        "suppressed": value.suppressed,
        "first_difference": value.first_difference,
    }


def _render_value(
    *,
    text: str,
    first_difference: int | None,
    options: DiffExampleRenderOptions,
) -> RenderedDiffExampleValue:
    original_length: int = len(text)
    if options.suppress_values:
        return RenderedDiffExampleValue(
            text=None,
            original_length=original_length,
            truncated=False,
            suppressed=True,
            first_difference=first_difference,
        )
    limit: int | None = options.max_value_length
    if limit is None or original_length <= limit:
        return RenderedDiffExampleValue(
            text=text,
            original_length=original_length,
            truncated=False,
            suppressed=False,
            first_difference=first_difference,
        )
    difference: int = first_difference or 0
    context_before: int = min(limit // 3, max(limit - 1, 0))
    start: int = min(max(difference - context_before, 0), original_length - limit)
    end: int = start + limit
    fragment: str = text[start:end]
    rendered: str = f"{'…' if start else ''}{fragment}{'…' if end < original_length else ''}"
    return RenderedDiffExampleValue(
        text=rendered,
        original_length=original_length,
        truncated=True,
        suppressed=False,
        first_difference=first_difference,
    )


def _first_difference(*, left: str, right: str) -> int | None:
    index: int
    for index, (left_char, right_char) in enumerate(zip(left, right, strict=False)):
        if left_char != right_char:
            return index
    if len(left) != len(right):
        return min(len(left), len(right))
    return None
