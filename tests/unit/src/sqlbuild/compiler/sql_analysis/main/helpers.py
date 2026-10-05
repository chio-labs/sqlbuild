"""Helpers for SQL analysis public-entry tests."""

from sqlbuild.compiler.sql_analysis.classes.binding_catalog import BindingCatalog
from sqlbuild.compiler.sql_analysis.types import NativeProjectCatalog


def nested_coalesce_sql(*, function_depth: int) -> str:
    expression: str = "value"
    for _ in range(function_depth):
        expression = f"COALESCE({expression}, 0)"
    return f"SELECT {expression} AS resolved_value FROM records"


def pool_catalog(dialect: str) -> NativeProjectCatalog:
    """Return a compile catalog, which normalizes batches on its analysis pool."""

    return BindingCatalog(
        dialect=dialect,
        quoted_ignore_case=False,
        known_functions=(),
        known_types=(),
        relations={},
    ).native


def without_catalog(dialect: str) -> None:
    """Return no catalog, which normalizes batches in turn."""

    _ = dialect
