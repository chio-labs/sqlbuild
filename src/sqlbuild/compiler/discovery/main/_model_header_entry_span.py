"""Public authored MODEL header entry span query."""

from __future__ import annotations

from sqlbuild.compiler.discovery._helpers.sql.model_files import (
    model_header_entry_span as _model_header_entry_span,
)


def get_model_header_entry_span(*, contents: str, key: str) -> tuple[int, int] | None:
    """Return authored byte offsets for one top-level `key value` MODEL header entry."""

    return _model_header_entry_span(contents=contents, key=key)
