"""dbt selector term helpers."""

from __future__ import annotations


def dbt_fqn_selector_term(*, fqn: tuple[str, ...], fallback: str) -> str:
    """Return the exact dbt FQN selector when available."""

    if fqn:
        return f"fqn:{'.'.join(fqn)}"
    return fallback
