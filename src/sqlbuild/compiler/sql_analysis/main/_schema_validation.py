"""Public schema-aware SQL validation query."""

from __future__ import annotations

from sqlbuild.compiler.sql_analysis._helpers.schema_validation import (
    get_schema_validations as _get_schema_validations,
)
from sqlbuild.compiler.sql_analysis.models import (
    SqlBindingResult,
    SqlSchemaValidationRequest,
)


def get_schema_validations(
    *, requests: tuple[SqlSchemaValidationRequest, ...]
) -> tuple[SqlBindingResult, ...]:
    """Return stable binding diagnostics for a batch of complete schemas."""

    return _get_schema_validations(requests=requests)
