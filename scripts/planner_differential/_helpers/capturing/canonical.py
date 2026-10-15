"""Mask run-specific values so two runs of the same tree compare equal."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

from scripts.compiler_differential.classes.capture_file import expand_capture_text
from scripts.planner_differential.constants import (
    COMPACT_TIMESTAMP_PATTERN,
    DATE_PATTERN,
    ELAPSED_TIME_MASK,
    ELAPSED_TIME_PATTERN,
    ISO_TIMESTAMP_PATTERN,
    MAPPING_MARKER,
    RECENT_TIMESTAMP_DAYS,
    RECENT_TIMESTAMP_MASK,
    RUN_RELATIVE_FUTURE_DAYS,
    RUN_RELATIVE_PAST_DAYS,
    VOLATILE_KEY_SUFFIXES,
    VOLATILE_KEYS,
    VOLATILE_VALUE_MASK,
)
from scripts.planner_differential.models import TextMasks
from sqlbuild._native import mask_capture_noise


def mask_text(*, text: str, masks: TextMasks) -> str:
    """Mask invocation ids, run paths, timestamps near the run date and run-relative dates."""

    masked: str = mask_capture_noise(text)
    for prefix, replacement in masks.replacements:
        masked = masked.replace(prefix, replacement)
    masked = ISO_TIMESTAMP_PATTERN.sub(
        lambda match: _recent_or_kept(match=match, today=masks.today, iso=True), masked
    )
    masked = COMPACT_TIMESTAMP_PATTERN.sub(
        lambda match: _recent_or_kept(match=match, today=masks.today, iso=False), masked
    )
    return DATE_PATTERN.sub(
        lambda match: _run_relative_date(match=match, today=masks.today), masked
    )


def mask_console_text(*, text: str, masks: TextMasks) -> str:
    """Mask console output: the artifact noise plus elapsed times."""

    return ELAPSED_TIME_PATTERN.sub(ELAPSED_TIME_MASK, mask_text(text=text, masks=masks))


def canonical_value(*, value: object, masks: TextMasks) -> object:
    """Return decoded JSON with volatile keys and run-specific text masked."""

    if isinstance(value, dict):
        canonical: dict[str, object] = {
            str(key): (
                VOLATILE_VALUE_MASK
                if item is not None and _volatile_key(str(key))
                else canonical_value(value=item, masks=masks)
            )
            for key, item in value.items()
        }
        pairs: object = canonical.get(MAPPING_MARKER)
        if len(canonical) == 1 and isinstance(pairs, list):
            return {MAPPING_MARKER: sorted(pairs, key=_sort_key)}
        return canonical
    if isinstance(value, list):
        return [canonical_value(value=item, masks=masks) for item in value]
    if isinstance(value, str):
        return mask_text(text=value, masks=masks)
    return value


def canonical_plan_capture(*, text: str, masks: TextMasks) -> object:
    """Expand a plan capture document's shared nodes and mask its volatile values."""

    return canonical_value(value=expand_capture_text(text), masks=masks)


def _volatile_key(key: str) -> bool:
    return key in VOLATILE_KEYS or key.endswith(VOLATILE_KEY_SUFFIXES)


def _sort_key(pair: object) -> str:
    key: object = pair[0] if isinstance(pair, list) and pair else pair
    return json.dumps(key, sort_keys=True, ensure_ascii=False)


def _recent_or_kept(*, match: re.Match[str], today: date, iso: bool) -> str:
    day_text: str = match.group(1)
    try:
        day: date = (
            date.fromisoformat(day_text)
            if iso
            else date(int(day_text[:4]), int(day_text[4:6]), int(day_text[6:]))
        )
    except ValueError:
        return match.group(0)
    recent: bool = day >= today - timedelta(days=RECENT_TIMESTAMP_DAYS)
    return RECENT_TIMESTAMP_MASK if recent else match.group(0)


def _run_relative_date(*, match: re.Match[str], today: date) -> str:
    """Write dates the planner derives from the run date, such as replay ranges, as offsets."""

    try:
        day: date = date.fromisoformat(match.group(1))
    except ValueError:
        return match.group(0)
    offset: int = (day - today).days
    if -RUN_RELATIVE_PAST_DAYS <= offset <= RUN_RELATIVE_FUTURE_DAYS:
        return f"<run-date{offset:+d}d>"
    return match.group(0)
