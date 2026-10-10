"""Typed SQL values as the plain values native consumers read."""

from sqlbuild.compiler.compiled_project._helpers.rows import typed_value_payload
from sqlbuild.sql_values.models import SqlValue


def plain_typed_value(value: SqlValue) -> object:
    """Return the value JSON-safe: decimals as text, collections and mappings recursively."""

    return typed_value_payload(value)
