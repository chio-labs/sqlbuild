"""Prepare shared native schema-validation inputs."""

from sqlbuild.compiler.sql_analysis._helpers.schema_validation import _request_payload
from sqlbuild.compiler.sql_analysis.models import SqlSchemaValidationRequest


def prepare_schema_validation(*, request: SqlSchemaValidationRequest) -> dict[str, object]:
    """Prepare the schema-validation protocol for native compilation."""
    return _request_payload(request=request)
