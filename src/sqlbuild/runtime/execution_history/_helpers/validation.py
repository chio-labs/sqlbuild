"""Execution history contract validation helpers."""

from datetime import UTC, datetime

from sqlbuild.runtime.execution_history.constants import MAX_PAGE_LIMIT
from sqlbuild.runtime.execution_history.exceptions import (
    InvalidFilterError,
    InvalidLimitError,
    ProjectionConsistencyError,
)


def validate_page_limit(limit: int) -> None:
    """Validate a positive, bounded storage page limit."""

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_LIMIT:
        raise InvalidLimitError(f"limit must be an integer from 1 through {MAX_PAGE_LIMIT}")


def validate_filter_text(*, value: str | None, field_name: str) -> None:
    """Validate an optional non-empty filter correlation value."""

    if value is not None and not value.strip():
        raise InvalidFilterError(f"{field_name} must be non-empty when provided")


def validate_filter_timestamp(*, value: datetime | None, field_name: str) -> None:
    """Validate an optional UTC filter boundary."""

    if value is not None and value.tzinfo is not UTC:
        raise InvalidFilterError(f"{field_name} must use UTC")


def validate_storage_timestamp(*, value: datetime, field_name: str) -> None:
    """Validate a UTC timestamp carried by a durable storage fact."""

    if value.tzinfo is not UTC:
        raise ProjectionConsistencyError(f"{field_name} must use UTC")
