"""Reconcile native unknown-function errors with project-owned declarations."""

import re

from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic

_UNKNOWN_FUNCTION_CODE: str = "B101"


def is_declared_function_diagnostic(
    *,
    diagnostic: SqlBindingDiagnostic,
    names: frozenset[str],
) -> bool:
    """Recognize only E202 for an explicitly known project function."""
    if diagnostic.code != _UNKNOWN_FUNCTION_CODE:
        return False
    message: str = re.sub(
        r"__sqlbuild_(?:udf|table_function)_", "", diagnostic.message, flags=re.IGNORECASE
    )
    return any(
        re.search(rf"(?<!\w){re.escape(name)}(?!\w)", message, re.IGNORECASE) for name in names
    )
