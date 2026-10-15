"""Presentation models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.presentation.constants import DEFAULT_MAX_DISPLAY_ENTRIES


@dataclass(frozen=True)
class DisplayOptions:
    """Options controlling bounded human output."""

    max_entries_per_section: int | None = DEFAULT_MAX_DISPLAY_ENTRIES
    overflow_flag: str = "--verbose"
