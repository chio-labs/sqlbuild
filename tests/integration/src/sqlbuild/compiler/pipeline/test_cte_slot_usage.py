"""Exercise the real compact native slot-usage boundary, including batch isolation."""

import json
from typing import Any

import pytest

import sqlbuild._native as native
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import NativeCteSlotCase


@pytest.mark.parametrize(
    "test_case",
    [
        NativeCteSlotCase(
            "WHERE-only literal origin is read",
            "WITH staged AS (SELECT 1 AS order_id, 2 AS priority), projected AS (SELECT order_id FROM staged WHERE priority > 0) SELECT order_id FROM projected",
            (),
        ),
        NativeCteSlotCase(
            "unused slot retains scope and ordinal",
            "WITH items AS (SELECT 1 AS order_id, 2 AS unused) SELECT order_id FROM items",
            (("root.ctes[0]", 1),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_slot_queries_when_crossing_native_boundary_then_compact_facts_are_complete(
    test_case: NativeCteSlotCase,
) -> None:
    results: list[dict[str, Any]] = json.loads(
        native.analyze_cte_slots_batch_json(
            json.dumps(
                {
                    "requests": [
                        {"sql": test_case.sql, "dialect": "duckdb"},
                        {"sql": "SELECT (", "dialect": "duckdb"},
                    ]
                }
            )
        )
    )
    assert len(results) == 2
    assert "Err" in results[1]
    facts: dict[str, Any] = results[0]["Ok"]
    assert facts["version"] == 1
    unused: tuple[tuple[str, int], ...] = tuple(
        sorted(
            (facts["strings"][facts["ctes"][slot[0]][0]], slot[1])
            for slot in filter(lambda slot: not slot[3], facts["slots"])
        )
    )
    assert unused == test_case.expected_unused


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-vv"]))
