"""Public entry point for portable typed warehouse-state SQL literals."""

from sqlbuild.sql_values._helpers.state_literal import (
    render_state_sql_literal as _render_state_sql_literal,
)
from sqlbuild.sql_values.types import StateSqlValueType


def render_state_sql_literal(*, value: object | None, declared_type: StateSqlValueType) -> str:
    """Render a Python value according to its declared state-column type."""

    return _render_state_sql_literal(value=value, declared_type=declared_type)
