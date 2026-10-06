"""Validation helpers for diff command arguments."""

from __future__ import annotations

from sqlbuild.cli.commands.exceptions import CliUserError


def parse_diff_name_range(name_range: str | None) -> tuple[str, str | None]:
    """Parse a diff name range in FROM:TO or FROM form; a bare FROM leaves TO unset."""

    if name_range is None:
        raise CliUserError("diff requires FROM:TO", code="C208")
    from_name: str
    separator: str
    to_name: str
    from_name, separator, to_name = name_range.partition(":")
    if not from_name or (separator and (not to_name or separator in to_name)):
        raise CliUserError("diff range must be FROM:TO or FROM", code="C209")
    return from_name, to_name or None
