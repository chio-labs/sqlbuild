"""Compare a stored view definition with the SELECT SQLBuild would create it from."""

from __future__ import annotations

from sqlbuild.adapter.contract._helpers.view_definitions import view_definitions_match


def same_view_definition(*, definition: str, sql: str) -> bool:
    """Return whether two view bodies match, ignoring quoting, case, whitespace, and CREATE."""

    return view_definitions_match(definition=definition, sql=sql)
