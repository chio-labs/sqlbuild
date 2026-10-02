"""Public change-policy value validation entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.authored_values._helpers.change_policy import change_policy_problem_impl


def change_policy_problem(*, key: str, value: object) -> str | None:
    """Describe why an on_schema_change or replay_on_change value is invalid, or return None."""

    return change_policy_problem_impl(key=key, value=value)
