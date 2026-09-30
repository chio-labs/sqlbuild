"""Model and column references in reusable SCHEMA declaration headers."""

from __future__ import annotations

from sqlbuild.compiler.refactoring._helpers.text.header_edits import (
    column_token_edits,
    model_name_token_edits,
    span_tokens,
)
from sqlbuild.compiler.refactoring.constants import SCHEMA_STATEMENT_PATTERN
from sqlbuild.compiler.refactoring.models import TextEdit


def schema_model_name_edits(*, contents: str, old: str, new: str) -> tuple[TextEdit, ...]:
    """Rename a model in every SCHEMA header of a declaration file."""

    edits: list[TextEdit] = []
    span: tuple[int, int]
    for span in _schema_spans(contents):
        edits.extend(
            model_name_token_edits(
                contents=contents,
                tokens=span_tokens(contents=contents, span=span),
                old=old,
                new=new,
            )
        )
    return tuple(edits)


def schema_column_edits(
    *, contents: str, upstream: str, old: str, new: str
) -> tuple[TextEdit, ...]:
    """Rename relationships `field` values pointing at a renamed column of a model."""

    edits: list[TextEdit] = []
    span: tuple[int, int]
    for span in _schema_spans(contents):
        edits.extend(
            column_token_edits(
                contents=contents,
                tokens=span_tokens(contents=contents, span=span),
                upstream=upstream,
                old=old,
                new=new,
            )
        )
    return tuple(edits)


def _schema_spans(contents: str) -> tuple[tuple[int, int], ...]:
    return tuple(
        (match.start("header"), match.end("header"))
        for match in SCHEMA_STATEMENT_PATTERN.finditer(contents)
    )
