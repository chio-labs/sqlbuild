"""Decode binding evidence from native compilation."""

from sqlbuild.compiler.sql_analysis._helpers.schema_validation import _binding_result
from sqlbuild.compiler.sql_analysis.models import SqlBindingResult


def decode_schema_validation(
    *, sql: str, dialect: str | None, response: object
) -> SqlBindingResult:
    """Decode binding evidence produced by either native compilation entry point."""
    return _binding_result(sql=sql, dialect=dialect, response=response)
