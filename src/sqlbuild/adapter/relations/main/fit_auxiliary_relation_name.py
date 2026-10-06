"""Auxiliary relation name fitting entrypoint."""

from __future__ import annotations

from sqlbuild.adapter.relations._helpers.identifier_fitting import (
    fit_auxiliary_relation_name_impl,
)


def fit_auxiliary_relation_name(*, base_name: str, suffix: str, identifier_limit: int) -> str:
    """Return ``base_name + suffix`` fitted within the limit, keeping the suffix and a base hash."""

    return fit_auxiliary_relation_name_impl(
        base_name=base_name, suffix=suffix, identifier_limit=identifier_limit
    )
