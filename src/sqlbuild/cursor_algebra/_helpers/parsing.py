"""Private cursor scalar parsing and rendering."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from sqlbuild.compiler.planner.types import CursorType
from sqlbuild.cursor_algebra.exceptions import CursorAlgebraError
from sqlbuild.cursor_algebra.models import DateValue, IntegerValue, TimestampValue
from sqlbuild.cursor_algebra.types import CursorScalar

_TRAILING_TIMEZONE_SEPARATOR: re.Pattern[str] = re.compile(r"\s+(?=(?:Z|[+-]\d{2}:?\d{2})$)")


def parse_scalar(*, raw: object, cursor_type: str) -> CursorScalar:
    """Parse one scalar while preserving temporal representation."""

    if cursor_type == CursorType.INTEGER:
        try:
            decimal_value: Decimal = Decimal(str(raw))
            integer_value: int = int(decimal_value)
        except (InvalidOperation, ValueError, OverflowError) as error:
            raise CursorAlgebraError(f"invalid integer cursor value: {raw}") from error
        if decimal_value != integer_value:
            raise CursorAlgebraError(f"non-integral integer cursor value: {raw}")
        return IntegerValue(value=integer_value)
    if cursor_type != CursorType.TIMESTAMP:
        raise CursorAlgebraError(f"unsupported cursor type: {cursor_type}")
    if isinstance(raw, datetime):
        return TimestampValue(value=_normalize_timestamp(value=raw))
    if isinstance(raw, date):
        return DateValue(value=raw)
    if not isinstance(raw, str):
        raise CursorAlgebraError(f"invalid timestamp cursor value: {raw}")
    normalized_text: str = _normalize_timestamp_text(value=raw)
    try:
        return DateValue(value=date.fromisoformat(normalized_text))
    except ValueError:
        try:
            return TimestampValue(
                value=_normalize_timestamp(value=datetime.fromisoformat(normalized_text)),
                source_text=normalized_text,
            )
        except ValueError as error:
            raise CursorAlgebraError(f"invalid timestamp cursor value: {raw}") from error


def render_scalar(*, value: CursorScalar) -> str:
    """Render one typed cursor scalar."""

    if isinstance(value, IntegerValue):
        return str(value.value)
    if isinstance(value, TimestampValue) and value.source_text is not None:
        return value.source_text
    return value.value.isoformat()


def _normalize_timestamp(*, value: datetime) -> datetime:
    """Normalize aware timestamps to UTC while leaving presumed-UTC naive values unchanged."""

    return value.astimezone(UTC) if value.tzinfo is not None else value


def _normalize_timestamp_text(*, value: str) -> str:
    """Normalize warehouse timestamp text into an ISO-compatible spelling."""

    return _TRAILING_TIMEZONE_SEPARATOR.sub("", value.strip())
