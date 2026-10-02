"""Exact TOML and MODEL-header snippets for diagnostics that name a setting."""

from __future__ import annotations

from sqlbuild.errors.setting_help.constants import (
    ADDITIONAL_HELP_SEPARATOR,
    HELP_CONTINUATION_INDENT,
    SETTING_SNIPPET_INDENT,
)
from sqlbuild.errors.setting_help.types import SettingValue


def toml_value(value: SettingValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    escaped: str = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def setting_snippet(*, section: str, key: str, value: SettingValue) -> str:
    return "\n".join(
        (
            f"{SETTING_SNIPPET_INDENT}[{section}]",
            f"{SETTING_SNIPPET_INDENT}{key} = {toml_value(value)}",
        )
    )


def setting_help(
    *, purpose: str, file_name: str, section: str, key: str, value: SettingValue
) -> str:
    snippet: str = setting_snippet(section=section, key=key, value=value)
    return f"{purpose}, set this in {file_name}:\n{snippet}"


def setting_note(
    *, file_name: str, section: str, key: str, value: SettingValue, explicit: bool | None
) -> str:
    rendered: str = toml_value(value)
    if explicit is None:
        return (
            f"the current value is [{section}] {key} = {rendered} (from {file_name} or its default)"
        )
    if explicit:
        return f"{file_name} sets [{section}] {key} = {rendered}"
    return f"{file_name} does not set [{section}] {key}, so it defaults to {rendered}"


def model_header_help(*, purpose: str, entry: str, follow_up: str | None) -> str:
    lines: list[str] = [
        f"{purpose}, add this to the MODEL header:",
        f"{SETTING_SNIPPET_INDENT}MODEL (",
        f"{SETTING_SNIPPET_INDENT}  {entry},",
        f"{SETTING_SNIPPET_INDENT}  ...",
        f"{SETTING_SNIPPET_INDENT});",
    ]
    if follow_up is not None:
        lines.append(f"{HELP_CONTINUATION_INDENT}{follow_up}")
    return "\n".join(lines)


def join_helps(helps: tuple[str, ...]) -> str:
    return ADDITIONAL_HELP_SEPARATOR.join(helps)
