"""Private cursor scalar parsing and rendering."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlbuild.compiler.planner.types import CursorType
from sqlbuild.cursor_algebra.exceptions import CursorAlgebraError
from sqlbuild.cursor_algebra.models import DateValue, IntegerValue, TimestampValue
from sqlbuild.cursor_algebra.types import CursorScalar


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
        return TimestampValue(value=raw)
    if isinstance(raw, date):
        return DateValue(value=raw)
    if not isinstance(raw, str):
        raise CursorAlgebraError(f"invalid timestamp cursor value: {raw}")
    try:
        return DateValue(value=date.fromisoformat(raw))
    except ValueError:
        try:
            return TimestampValue(value=datetime.fromisoformat(raw))
        except ValueError as error:
            raise CursorAlgebraError(f"invalid timestamp cursor value: {raw}") from error


def render_scalar(*, value: CursorScalar) -> str:
    """Render one typed cursor scalar."""

    if isinstance(value, IntegerValue):
        return str(value.value)
    return value.value.isoformat()
