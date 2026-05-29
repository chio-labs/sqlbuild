"""Semantic styling helpers for human CLI output."""

from __future__ import annotations

from sqlbuild.shared.models import CliTheme, TextStyle

_BOLD: str = "\033[1m"
_DIM: str = "\033[2m"
_RED: str = "\033[31m"
_GREEN: str = "\033[32m"
_YELLOW: str = "\033[33m"
_BLUE: str = "\033[34m"
_ORANGE: str = "\033[38;5;208m"

default_cli_theme: CliTheme = CliTheme(
    title=TextStyle(_GREEN + _BOLD),
    section=TextStyle(_BOLD),
    label=TextStyle(_DIM),
    value=TextStyle(_BLUE + _BOLD),
    accent=TextStyle(_BLUE),
    object_name=TextStyle(_BLUE + _BOLD),
    command=TextStyle(_DIM),
    success=TextStyle(_GREEN),
    success_strong=TextStyle(_GREEN + _BOLD),
    warning=TextStyle(_YELLOW),
    warning_strong=TextStyle(_YELLOW + _BOLD),
    error=TextStyle(_RED),
    error_strong=TextStyle(_RED + _BOLD),
    error_muted=TextStyle(_RED + _DIM),
    log_label=TextStyle(_BLUE + _DIM),
    skipped=TextStyle(_DIM),
    muted=TextStyle(_DIM),
    dbt_section=TextStyle(_ORANGE + _BOLD),
    dbt_label=TextStyle(_ORANGE),
    dbt_object_name=TextStyle(_ORANGE + _BOLD),
    dbt_execution_label=TextStyle(_ORANGE + _BOLD),
)


class CliStyle:
    """Semantic CLI styling facade used by human-output formatters."""

    def __init__(self, *, use_color: bool, theme: CliTheme = default_cli_theme) -> None:
        self.use_color: bool = use_color
        self.theme: CliTheme = theme

    def title(self, text: str) -> str:
        return self.theme.title.apply(text, use_color=self.use_color)

    def section(self, text: str) -> str:
        return self.theme.section.apply(text, use_color=self.use_color)

    def label(self, text: str) -> str:
        return self.theme.label.apply(text, use_color=self.use_color)

    def value(self, text: str) -> str:
        return self.theme.value.apply(text, use_color=self.use_color)

    def accent(self, text: str) -> str:
        return self.theme.accent.apply(text, use_color=self.use_color)

    def object_name(self, text: str) -> str:
        return self.theme.object_name.apply(text, use_color=self.use_color)

    def command(self, text: str) -> str:
        return self.theme.command.apply(text, use_color=self.use_color)

    def muted(self, text: str) -> str:
        return self.theme.muted.apply(text, use_color=self.use_color)

    def success(self, text: str) -> str:
        return self.theme.success.apply(text, use_color=self.use_color)

    def success_strong(self, text: str) -> str:
        return self.theme.success_strong.apply(text, use_color=self.use_color)

    def warning(self, text: str) -> str:
        return self.theme.warning.apply(text, use_color=self.use_color)

    def warning_strong(self, text: str) -> str:
        return self.theme.warning_strong.apply(text, use_color=self.use_color)

    def error(self, text: str) -> str:
        return self.theme.error.apply(text, use_color=self.use_color)

    def error_strong(self, text: str) -> str:
        return self.theme.error_strong.apply(text, use_color=self.use_color)

    def error_muted(self, text: str) -> str:
        return self.theme.error_muted.apply(text, use_color=self.use_color)

    def log_label(self, text: str) -> str:
        return self.theme.log_label.apply(text, use_color=self.use_color)

    def dbt_section(self, text: str) -> str:
        return self.theme.dbt_section.apply(text, use_color=self.use_color)

    def dbt_label(self, text: str) -> str:
        return self.theme.dbt_label.apply(text, use_color=self.use_color)

    def dbt_object_name(self, text: str) -> str:
        return self.theme.dbt_object_name.apply(text, use_color=self.use_color)

    def dbt_execution_label(self, text: str) -> str:
        return self.theme.dbt_execution_label.apply(text, use_color=self.use_color)

    def status(self, status: str, text: str | None = None) -> str:
        """Style status text according to the status word."""

        rendered: str = status if text is None else text
        normalized: str = status.upper()
        if normalized in {"OK", "PASS", "SUCCESS"}:
            return self.theme.success.apply(rendered, use_color=self.use_color)
        if normalized in {"WARN", "WARNING"}:
            return self.theme.warning.apply(rendered, use_color=self.use_color)
        if normalized in {"FAIL", "FAILED", "ERROR"}:
            return self.theme.error.apply(rendered, use_color=self.use_color)
        if normalized in {"SKIP", "SKIPPED"}:
            return self.theme.skipped.apply(rendered, use_color=self.use_color)
        return rendered
