from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedSqlTestPlanningParityTestCase:
    """Seeded SQL-test projects the native planning glue and the JSON request must agree on."""

    description: str
    seed: int
    count: int
    test_count: int
    adapter_names: tuple[str, ...]
    expected_minimum_planned: int
    expected_minimum_with_errors: int
    expected_minimum_raised: int
