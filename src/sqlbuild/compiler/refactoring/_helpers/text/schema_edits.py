"""Model and column references in reusable SCHEMA declaration headers."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.compiler.refactoring._helpers.text.header_edits import (
    column_token_edits,
    model_name_token_edits,
    span_tokens,
)
from sqlbuild.compiler.refactoring.constants import SCHEMA_STATEMENT_PATTERN
from sqlbuild.compiler.refactoring.models import HeaderToken, TextEdit


def schema_model_name_edits(*, contents: str, old: str, new: str) -> tuple[TextEdit, ...]:
    """Rename a model in every SCHEMA header of a declaration file."""

    return _each_schema(
        contents=contents,
        edit=lambda tokens: model_name_token_edits(
            contents=contents, tokens=tokens, old=old, new=new
        ),
    )


def schema_column_edits(
    *, contents: str, upstream: str, old: str, new: str
) -> tuple[TextEdit, ...]:
    """Rename relationships `field` values pointing at a renamed column of a model."""

    return _each_schema(
        contents=contents,
        edit=lambda tokens: column_token_edits(
            contents=contents, tokens=tokens, upstream=upstream, old=old, new=new
        ),
    )


def _each_schema(
    *, contents: str, edit: Callable[[tuple[HeaderToken, ...]], tuple[TextEdit, ...]]
) -> tuple[TextEdit, ...]:
    edits: list[TextEdit] = []
    for match in SCHEMA_STATEMENT_PATTERN.finditer(contents):
        edits.extend(
            edit(span_tokens(contents=contents, span=(match.start("header"), match.end("header"))))
        )
    return tuple(edits)
