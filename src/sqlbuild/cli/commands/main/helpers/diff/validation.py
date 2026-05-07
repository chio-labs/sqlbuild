"""Validation helpers for diff command arguments."""

from __future__ import annotations

from sqlbuild.cli.commands.main.shared.exceptions import CliUserError


def parse_diff_environment_range(environment_range: str | None) -> tuple[str, str]:
    """Parse a diff environment range in FROM:TO form."""

    if environment_range is None:
        raise CliUserError("diff requires FROM:TO", code="C208")
    if environment_range.count(":") != 1:
        raise CliUserError("diff environment range must be FROM:TO", code="C209")
    from_environment: str
    to_environment: str
    from_environment, to_environment = environment_range.split(":", 1)
    if not from_environment or not to_environment:
        raise CliUserError("diff environment range must be FROM:TO", code="C209")
    return from_environment, to_environment
