"""Explain expected-output columns that a model does not produce."""

from __future__ import annotations

from sqlbuild.executor.testing.constants import SQL_TEST_IDENTIFIER_QUOTES


def describe_missing_expected_columns(
    *,
    model_name: str,
    expected_columns: tuple[str, ...],
    available_columns: frozenset[str],
) -> str | None:
    """Describe listed expected columns absent from casefolded model output names."""

    missing: tuple[str, ...] = tuple(
        column
        for column in expected_columns
        if _normalized_identifier(column) not in available_columns
    )
    if not missing:
        return None
    return (
        f"expected output '{model_name}' lists columns that model '{model_name}' does not "
        f"output: {', '.join(missing)}. Expected CTEs are compared only on the columns they "
        "list, matched by name"
    )


def _normalized_identifier(identifier: str) -> str:
    closing_quote: str | None = SQL_TEST_IDENTIFIER_QUOTES.get(identifier[:1])
    if closing_quote is None or not identifier.endswith(closing_quote):
        return identifier.casefold()
    return identifier[1:-1].replace(closing_quote * 2, closing_quote).casefold()
