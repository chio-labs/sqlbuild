"""Validation of authored on_schema_change and replay_on_change values."""

from __future__ import annotations

from sqlbuild.compiler.planner.types import BackfillAction, OnSchemaChange
from sqlbuild.cursor_algebra.models import Duration
from sqlbuild.errors.setting_help.main.model_header_help import model_header_help
from sqlbuild.errors.setting_help.main.setting_help import setting_help

_ON_SCHEMA_CHANGE_KEY: str = "on_schema_change"
_REPLAY_ON_CHANGE_KEY: str = "replay_on_change"
_BOUNDED_PREFIX: str = f"{BackfillAction.BOUNDED}-"
_VALID_VALUES: dict[str, tuple[str, ...]] = {
    _ON_SCHEMA_CHANGE_KEY: tuple(sorted(policy.value for policy in OnSchemaChange)),
    _REPLAY_ON_CHANGE_KEY: (
        BackfillAction.FORWARD_ONLY.value,
        BackfillAction.FULL.value,
        f"{_BOUNDED_PREFIX}<duration>",
    ),
}
_EXAMPLE_VALUES: dict[str, str] = {
    _ON_SCHEMA_CHANGE_KEY: OnSchemaChange.APPEND_NEW_COLUMNS.value,
    _REPLAY_ON_CHANGE_KEY: f"{_BOUNDED_PREFIX}14d",
}


def change_policy_problem_impl(*, key: str, value: object) -> str | None:
    """Describe why a change-policy value is invalid, or return None when it is valid."""

    valid: str = ", ".join(_VALID_VALUES[key])
    if not isinstance(value, str):
        return f"{key} must be a string; valid values: {valid}"
    if key == _ON_SCHEMA_CHANGE_KEY and value in _VALID_VALUES[key]:
        return None
    if key == _REPLAY_ON_CHANGE_KEY:
        if value in (BackfillAction.FORWARD_ONLY, BackfillAction.FULL):
            return None
        if value.startswith(_BOUNDED_PREFIX):
            duration: str = value.removeprefix(_BOUNDED_PREFIX).strip()
            if Duration.parse(duration) is not None:
                return None
            return (
                f"{key} '{value}' has an invalid duration '{duration}'; use a positive duration "
                "such as 14d, 12h or 1mo"
            )
    return f"unknown {key} '{value}'; valid values: {valid}"


def change_policy_header_help_impl(*, key: str) -> str:
    """Show a valid MODEL header entry for a change-policy key."""

    return model_header_help(purpose=f"use a valid {key}", entry=f"{key} {_EXAMPLE_VALUES[key]}")


def change_policy_toml_help_impl(*, key: str, file_name: str, section: str) -> str:
    """Show a valid TOML setting line for a change-policy key."""

    return setting_help(
        purpose=f"use a valid {key}",
        file_name=file_name,
        section=section,
        key=key,
        value=_EXAMPLE_VALUES[key],
    )
