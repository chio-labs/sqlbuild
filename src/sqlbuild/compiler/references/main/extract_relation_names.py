"""Relation-name extraction entrypoint for hard-coded name checks."""

from __future__ import annotations

from sqlbuild.compiler.references._helpers.relation_names import extract_relation_names_impl
from sqlbuild.compiler.references.models import RelationName


def extract_relation_names(
    *, sql: str, dialect: str | None
) -> tuple[tuple[RelationName, ...], frozenset[str]] | None:
    """Return relations named in ``sql`` and temporary tables it creates, or None if unparseable."""

    return extract_relation_names_impl(sql=sql, dialect=dialect)
