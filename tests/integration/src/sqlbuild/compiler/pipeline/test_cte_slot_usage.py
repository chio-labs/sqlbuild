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
            "local reads remain distinct from downstream output reads",
            "WITH items AS (SELECT 1 AS priority, priority + 1 AS amount) SELECT amount FROM items",
            (("root.ctes[0]", 0),),
            "snowflake",
            expected_local_reads=((0, 0),),
        ),
        NativeCteSlotCase(
            "diagnosed missing column remains a validation error rather than missing usage facts",
            "WITH items AS (SELECT 1 AS order_id, 2 AS unused) SELECT order_id FROM items WHERE missing > 0",
            (("root.ctes[0]", 1),),
            strict=True,
            expected_valid=False,
        ),
        NativeCteSlotCase(
            "open physical input preserves named output identities",
            "WITH staged AS (SELECT o.order_id, o.status FROM orders o) SELECT order_id FROM staged",
            (("root.ctes[0]", 1),),
            "snowflake",
        ),
        NativeCteSlotCase(
            "unknown star does not hide unread named output",
            "WITH staged AS (SELECT o.*, 1 AS priority, 2 AS unused FROM orders o) SELECT priority FROM staged",
            (("root.ctes[0]", 2),),
            "snowflake",
            expected_partial_ctes=(0,),
        ),
        NativeCteSlotCase(
            "partial star pass-through reads every known named input",
            "WITH staged AS (SELECT o.*, 1 AS priority FROM orders o), passed AS (SELECT * FROM staged) SELECT priority FROM passed",
            (),
            "snowflake",
            expected_partial_ctes=(0, 1),
        ),
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
        NativeCteSlotCase(
            "Snowflake normalizes CTE declarations and reads together",
            "WITH staged AS (SELECT 1 AS order_id, 2 AS priority), projected AS (SELECT order_id FROM staged WHERE priority > 0) SELECT order_id FROM projected",
            (),
            "snowflake",
        ),
        NativeCteSlotCase(
            "Snowflake relation alias binds its consumed output",
            "WITH items AS (SELECT 1 AS order_id, 2 AS unused) SELECT t.order_id FROM items AS t",
            (("root.ctes[0]", 1),),
            "snowflake",
        ),
        NativeCteSlotCase(
            "Snowflake lateral output and captured input slots",
            "WITH items AS (SELECT 1 AS x, 2 AS y, 3 AS unused) SELECT f.value FROM items, LATERAL FLATTEN(INPUT => ARRAY_CONSTRUCT(items.x, items.y)) f",
            (("root.ctes[0]", 2),),
            "snowflake",
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
                        {
                            "sql": test_case.sql,
                            "dialect": test_case.dialect,
                            "schema": {"tables": [], "strict": test_case.strict},
                        },
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
    assert tuple(facts["partial_ctes"]) == test_case.expected_partial_ctes
    assert tuple(tuple(slot) for slot in facts["local_reads"]) == test_case.expected_local_reads
    unused: tuple[tuple[str, int], ...] = tuple(
        sorted(
            (facts["strings"][facts["ctes"][slot[0]][0]], slot[1])
            for slot in filter(lambda slot: not slot[3], facts["slots"])
        )
    )
    assert unused == test_case.expected_unused
    validation: dict[str, Any] = json.loads(
        native.validate_sql_with_schema_json(
            json.dumps(
                {
                    "sql": test_case.sql,
                    "dialect": test_case.dialect,
                    "schema": {"tables": [], "strict": test_case.strict},
                }
            )
        )
    )
    assert validation["valid"] is test_case.expected_valid


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-vv"]))
