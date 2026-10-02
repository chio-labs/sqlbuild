"""Public TOML help entrypoint for change-policy values."""

from __future__ import annotations

from sqlbuild.compiler.authored_values._helpers.change_policy import change_policy_toml_help_impl


def change_policy_toml_help(*, key: str, file_name: str, section: str) -> str:
    """Show a valid TOML setting line for on_schema_change or replay_on_change."""

    return change_policy_toml_help_impl(key=key, file_name=file_name, section=section)
