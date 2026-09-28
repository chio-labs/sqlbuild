"""Order relation grants for replay and drop column grants a view does not expose."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import RelationGrant


def grants_for_columns(
    *, grants: tuple[RelationGrant, ...], columns: tuple[str, ...]
) -> tuple[RelationGrant, ...]:
    """Return relation-level grants, then column grants on exposed columns only."""

    exposed: frozenset[str] = frozenset(column.lower() for column in columns)
    return (
        *(grant for grant in grants if grant.column is None),
        *(
            grant
            for grant in grants
            if grant.column is not None and grant.column.lower() in exposed
        ),
    )
