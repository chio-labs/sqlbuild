"""Presentation models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.presentation.constants import DEFAULT_MAX_DISPLAY_ENTRIES


@dataclass(frozen=True)
class DisplayOptions:
    """Options controlling bounded human output."""

    max_entries_per_section: int | None = DEFAULT_MAX_DISPLAY_ENTRIES
    overflow_flag: str = "--verbose"


@dataclass(frozen=True)
class TextStyle:
    """One ANSI style role in the CLI theme."""

    prefix: str
    suffix: str = "\033[0m"

    def apply(self, *, text: str, use_color: bool) -> str:
        """Apply this style when color is enabled."""

        if not use_color or not self.prefix or not text:
            return text
        return f"{self.prefix}{text}{self.suffix}"


@dataclass(frozen=True)
class CliTheme:
    """Semantic style roles for human CLI output."""

    title: TextStyle
    section: TextStyle
    label: TextStyle
    value: TextStyle
    accent: TextStyle
    plan_section: TextStyle
    object_name: TextStyle
    command: TextStyle
    success: TextStyle
    success_strong: TextStyle
    warning: TextStyle
    warning_strong: TextStyle
    error: TextStyle
    error_strong: TextStyle
    error_muted: TextStyle
    log_label: TextStyle
    skipped: TextStyle
    muted: TextStyle
    dbt_section: TextStyle
    dbt_label: TextStyle
    dbt_object_name: TextStyle
    dbt_execution_label: TextStyle
