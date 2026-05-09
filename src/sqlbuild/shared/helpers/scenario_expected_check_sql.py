"""SQL builders for scenario expected-output checks."""

from __future__ import annotations


def build_scenario_expected_comparison_sql(
    *,
    actual_sql: str,
    expected_sql: str,
    set_difference_operator: str,
) -> str:
    """Build SQL that compares actual scenario output to expected SQL."""

    return (
        "WITH "
        f"__actual AS ({actual_sql}), "
        f"__expected AS ({expected_sql}) "
        "SELECT "
        "(SELECT COUNT(*) FROM __actual) AS actual_count, "
        "(SELECT COUNT(*) FROM __expected) AS expected_count, "
        "(SELECT COUNT(*) FROM ("
        f"SELECT * FROM __actual {set_difference_operator} SELECT * FROM __expected"
        ")) AS mismatched_count"
    )
