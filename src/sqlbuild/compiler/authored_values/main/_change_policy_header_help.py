"""Public MODEL-header help entrypoint for change-policy values."""

from __future__ import annotations

from sqlbuild.compiler.authored_values._helpers.change_policy import (
    change_policy_header_help_impl,
)


def change_policy_header_help(*, key: str) -> str:
    """Show a valid MODEL header entry for on_schema_change or replay_on_change."""

    return change_policy_header_help_impl(key=key)
