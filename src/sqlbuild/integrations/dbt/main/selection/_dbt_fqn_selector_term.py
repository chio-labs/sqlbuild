"""Build a dbt FQN selector term."""

from sqlbuild.integrations.dbt._helpers.selection.selector_terms import (
    dbt_fqn_selector_term as _build,
)


def dbt_fqn_selector_term(*, fqn: tuple[str, ...], fallback: str) -> str:
    """Return the most specific stable dbt selector term."""

    return _build(fqn=fqn, fallback=fallback)
