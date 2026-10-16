"""Helpers for fixture type-scope integration tests."""


def unrelated_source_entries(*, count: int) -> str:
    """Source YAML entries for relations no fixture chain reads."""
    return "".join(
        f"  - name: unrelated_orders_{index}\n    description: Unrelated input.\n"
        "    expression: SELECT 1 AS order_id\n"
        "    columns:\n      - name: order_id\n        type: INTEGER\n"
        for index in range(count)
    )
