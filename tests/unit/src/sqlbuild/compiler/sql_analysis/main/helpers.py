"""Helpers for SQL analysis public-entry tests."""


def nested_coalesce_sql(*, function_depth: int) -> str:
    expression: str = "value"
    for _ in range(function_depth):
        expression = f"COALESCE({expression}, 0)"
    return f"SELECT {expression} AS resolved_value FROM records"
