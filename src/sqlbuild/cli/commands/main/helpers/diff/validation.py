"""Validation helpers for diff command arguments."""

from __future__ import annotations

from sqlbuild.cli.commands.main.shared.exceptions import CliUserError


def parse_diff_target_range(target_range: str | None) -> tuple[str, str]:
    """Parse a diff environment range in FROM:TO form."""

    if target_range is None:
        raise CliUserError("diff requires FROM:TO", code="C208")
    if target_range.count(":") != 1:
        raise CliUserError("diff environment range must be FROM:TO", code="C209")
    from_target: str
    to_target: str
    from_target, to_target = target_range.split(":", 1)
    if not from_target or not to_target:
        raise CliUserError("diff environment range must be FROM:TO", code="C209")
    return from_target, to_target
