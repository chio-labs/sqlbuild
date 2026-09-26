use serde_json::{Value, json};
use std::collections::BTreeSet;

use polyglot_sql::DialectType;

use crate::query_analysis::cte_usage::analyze;
use crate::query_analysis::tests::test_types::CteUsageTestCase;

#[test]
fn given_batched_slot_queries_when_one_is_invalid_then_compact_results_preserve_order()
-> Result<(), String> {
    let test_cases = [CteUsageTestCase {
        description: "batch error isolation and compact slot identities",
        sql: "WITH items AS (SELECT 1 AS order_id, 2 AS unused) SELECT order_id FROM items",
        expected_unused: &[("root.ctes[0]", 1)],
        expected_required: &[],
    }];
    for test_case in test_cases {
        let payload = json!({"requests":[
            {"sql":test_case.sql,"dialect":"duckdb"},
            {"sql":"SELECT (","dialect":"duckdb"},
            {"sql":test_case.sql,"dialect":"duckdb"}
        ]});
        let response =
            crate::query_analysis::main::analyze_cte_slots::analyze_cte_slots_batch_json(
                &payload.to_string(),
            )?;
        let results: Value = serde_json::from_str(&response).map_err(|error| error.to_string())?;
        assert_eq!(results[0], results[2], "{}", test_case.description);
        assert!(results[1]["Err"].is_string(), "{}", test_case.description);
        assert_eq!(results[0]["Ok"]["version"], 1);
        let slots = results[0]["Ok"]["slots"]
            .as_array()
            .ok_or("Missing compact slots")?;
        assert_eq!(
            slots.iter().filter(|slot| slot[3] == false).count(),
            test_case.expected_unused.len()
        );
    }
    Ok(())
}

#[test]
fn given_scoped_cte_references_when_binding_usage_then_slot_identity_and_reads_are_preserved()
-> Result<(), String> {
    let test_cases = [
        CteUsageTestCase {
            description: "WHERE-only literal-origin read",
            sql: "WITH staged AS (SELECT 1 AS order_id, 2 AS priority), projected AS (SELECT order_id FROM staged WHERE priority > 0) SELECT order_id FROM projected",
            expected_unused: &[],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "qualified relation alias",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y) SELECT t.x AS renamed FROM a AS t",
            expected_unused: &[("root.ctes[0]", 1)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "star reads every upstream slot",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y), b AS (SELECT * FROM a) SELECT x FROM b",
            expected_unused: &[("root.ctes[1]", 1)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "qualified star reads every upstream slot",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y), b AS (SELECT a.* FROM a) SELECT x FROM b",
            expected_unused: &[("root.ctes[1]", 1)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "relation alias column list",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y) SELECT t.v FROM a AS t(v,w)",
            expected_unused: &[("root.ctes[0]", 1)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "unqualified renamed relation column",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y) SELECT v FROM a AS t(v,w)",
            expected_unused: &[("root.ctes[0]", 1)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "CTE declared column list",
            sql: "WITH a(v,w) AS (SELECT 1 AS x, 2 AS y) SELECT v FROM a",
            expected_unused: &[("root.ctes[0]", 1)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "partial CTE column list",
            sql: "WITH a(v) AS (SELECT 1 AS x, 2 AS y) SELECT y FROM a",
            expected_unused: &[("root.ctes[0]", 0)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "partial CTE column list with star",
            sql: "WITH a(v) AS (SELECT 1 AS x, 2 AS y) SELECT * FROM a",
            expected_unused: &[],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "CASE and function arguments",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y) SELECT CASE WHEN x > 0 THEN ABS(y) ELSE 0 END FROM a",
            expected_unused: &[],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "JOIN USING reads both inputs",
            sql: "WITH a AS (SELECT 1 AS id, 2 AS extra), b AS (SELECT 1 AS id, 3 AS value) SELECT b.value FROM a JOIN b USING(id)",
            expected_unused: &[("root.ctes[0]", 1)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "JOIN ON reads both inputs",
            sql: "WITH a AS (SELECT 1 AS id, 2 AS extra), b AS (SELECT 1 AS id, 3 AS value) SELECT b.value FROM a JOIN b ON a.id = b.id",
            expected_unused: &[("root.ctes[0]", 1)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "GROUP HAVING ORDER",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y, 3 AS unused) SELECT COUNT(*) FROM a GROUP BY x HAVING SUM(y) > 0 ORDER BY x",
            expected_unused: &[("root.ctes[0]", 2)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "QUALIFY and window clauses",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y, 3 AS unused) SELECT x FROM a QUALIFY ROW_NUMBER() OVER (PARTITION BY x ORDER BY y) = 1",
            expected_unused: &[("root.ctes[0]", 2)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "correlated subquery",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y) SELECT x FROM a WHERE EXISTS (SELECT 1 WHERE a.y > 0)",
            expected_unused: &[],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "correlated unqualified name with shadowed qualifier",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y), b AS (SELECT 3 AS x) SELECT (SELECT y FROM b AS t) FROM a AS t",
            expected_unused: &[("root.ctes[0]", 0), ("root.ctes[1]", 0)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "uncorrelated scalar subquery",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y) SELECT (SELECT x FROM a)",
            expected_unused: &[("root.ctes[0]", 1)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "nested shadowing",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y), b AS (WITH a AS (SELECT 3 AS x, 4 AS y) SELECT x FROM a) SELECT a.y, b.x FROM a CROSS JOIN b",
            expected_unused: &[("root.ctes[0]", 0), ("root.ctes[1].ctes[0]", 1)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "physical alias shadows CTE declaration",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y) SELECT a.x FROM orders AS a",
            expected_unused: &[("root.ctes[0]", 0), ("root.ctes[0]", 1)],
            expected_required: &[],
        },
        CteUsageTestCase {
            description: "set branch inputs",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y) SELECT x FROM a UNION SELECT x FROM a",
            expected_unused: &[("root.ctes[0]", 1)],
            expected_required: &[("root.ctes[0]", 0)],
        },
        CteUsageTestCase {
            description: "set operation output slots",
            sql: "WITH a AS (SELECT 1 AS x, 2 AS y UNION SELECT 3 AS x, 4 AS y) SELECT x FROM a",
            expected_unused: &[("root.ctes[0]", 1)],
            expected_required: &[("root.ctes[0]", 0), ("root.ctes[0]", 1)],
        },
    ];
    for test_case in test_cases {
        let expression = polyglot_sql::parse(test_case.sql, DialectType::DuckDB)
            .map_err(|error| error.to_string())?
            .remove(0);
        let facts = analyze(&expression, None, DialectType::DuckDB)
            .map_err(|error| format!("{}: {error}", test_case.description))?;
        let unused: BTreeSet<_> = facts
            .iter()
            .flat_map(|cte| {
                cte.slots
                    .iter()
                    .enumerate()
                    .filter(|(_, slot)| !slot.read)
                    .map(|(index, _)| (cte.scope.as_str(), index))
            })
            .collect();
        let required: BTreeSet<_> = facts
            .iter()
            .flat_map(|cte| {
                cte.slots
                    .iter()
                    .enumerate()
                    .filter(|(_, slot)| slot.semantically_required)
                    .map(|(index, _)| (cte.scope.as_str(), index))
            })
            .collect();
        assert_eq!(
            unused,
            test_case.expected_unused.iter().copied().collect(),
            "{}",
            test_case.description
        );
        assert_eq!(
            required,
            test_case.expected_required.iter().copied().collect(),
            "{}",
            test_case.description
        );
    }
    Ok(())
}
