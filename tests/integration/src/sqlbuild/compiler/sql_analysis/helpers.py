"""Relation-name extraction outcomes for SQL analysis tests."""

from __future__ import annotations

from typing import cast

from sqlbuild.compiler.references.main.extract_relation_names import extract_relation_names
from sqlbuild.compiler.references.models import RelationName
from tests.integration.src.sqlbuild.compiler.compile.helpers import ExpansionFailureCapture


def relation_names_outcome(sql: str, dialect: str | None) -> object:
    """The extracted `(relations, sorted temporary names)`, None if unparseable, or the error."""

    capture: ExpansionFailureCapture = ExpansionFailureCapture()
    extracted: list[tuple[tuple[RelationName, ...], frozenset[str]] | None] = [None]
    with capture:
        extracted[0] = extract_relation_names(sql=sql, dialect=dialect)
    return {
        True: lambda: _relation_view(extracted[0]),
        False: lambda: (type(capture.failure).__name__, str(capture.failure)),
    }[capture.failure is None]()


def _relation_view(
    extracted: tuple[tuple[RelationName, ...], frozenset[str]] | None,
) -> object:
    return {
        True: lambda: None,
        False: lambda: _present_relation_view(
            cast(tuple[tuple[RelationName, ...], frozenset[str]], extracted)
        ),
    }[extracted is None]()


def _present_relation_view(
    extracted: tuple[tuple[RelationName, ...], frozenset[str]],
) -> tuple[tuple[tuple[str, str | None, str | None], ...], tuple[str, ...]]:
    relations, temporary = extracted
    return (
        tuple((relation.name, relation.schema, relation.database) for relation in relations),
        tuple(sorted(temporary)),
    )
