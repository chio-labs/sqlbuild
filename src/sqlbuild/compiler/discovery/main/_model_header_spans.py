"""Public authored MODEL header span queries."""

from __future__ import annotations

from sqlbuild.compiler.discovery._helpers.sql.model_files import (
    model_header_body_span as _model_header_body_span,
)
from sqlbuild.compiler.discovery._helpers.sql.model_files import (
    model_header_columns_span as _model_header_columns_span,
)
from sqlbuild.compiler.discovery.models import ModelHeaderSpans


def get_model_header_spans(*, contents: str) -> ModelHeaderSpans:
    """Return authored byte offsets for the MODEL header and column declarations."""

    return ModelHeaderSpans(
        body=_model_header_body_span(contents=contents),
        columns=_model_header_columns_span(contents=contents),
    )
