from __future__ import annotations

from sqlbuild.versioned.state.types import StateColumnType


def state_type_matches_for_test(actual_type: str, expected_type: StateColumnType) -> bool:
    return actual_type.lower() == expected_type.value or (
        expected_type == StateColumnType.TEXT and actual_type.lower() == "varchar"
    )
