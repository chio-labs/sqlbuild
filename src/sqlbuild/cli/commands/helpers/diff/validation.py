"""Validation helpers for diff command arguments."""

from __future__ import annotations

from sqlbuild.cli.commands.shared.exceptions import CliUserError


def parse_diff_name_range(name_range: str | None) -> tuple[str, str]:
    """Parse a diff name range in FROM:TO form."""

    if name_range is None:
        raise CliUserError("diff requires FROM:TO", code="C208")
    if name_range.count(":") != 1:
        raise CliUserError("diff range must be FROM:TO", code="C209")
    from_name: str
    to_name: str
    from_name, to_name = name_range.split(":", 1)
    if not from_name or not to_name:
        raise CliUserError("diff range must be FROM:TO", code="C209")
    return from_name, to_name
