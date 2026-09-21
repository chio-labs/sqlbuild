use crate::query_analysis::main::analyze_project_compact_json;
use serde_json::{Value, json};

pub(crate) fn widening_aggregates_require_compatibility_recovery() -> bool {
    for expression in [
        "AVG(order_id)",
        "SUM(order_id)",
        "MIN(order_id) > 0",
        "MIN(order_id) / 2.0",
    ] {
        for rich in [false, true] {
            let response: Value = serde_json::from_str(
                &analyze_project_compact_json(&json!({
                    "queries": [{"sql": format!("WITH selected AS (SELECT CAST(1 AS BIGINT) AS order_id) SELECT {expression} AS result FROM selected"), "dialect": "duckdb"}],
                    "templates": [{"queryIndex": 0, "recoverCteFacts": true, "richTypeInference": rich}],
                    "projections": [{"templateIndex": 0}]
                }).to_string()).expect("query should analyze"),
            ).expect("response should decode");
            assert_eq!(
                response["templates"][0],
                "native project type recovery requires legacy fallback"
            );
        }
    }
    true
}

pub(crate) fn compact_project_query_interns_repeated_lineage_strings() -> bool {
    let response: Value = serde_json::from_str(
        &analyze_project_compact_json(
            &json!({
                "queries": [{
                    "sql": "SELECT order_id FROM orders",
                    "dialect": "duckdb",
                    "schema": {"tables": [{
                        "name": "orders",
                        "columns": [{"name": "order_id", "type": "BIGINT", "nullable": false}]
                    }]}
                }],
                "templates": [{
                    "queryIndex": 0,
                    "references": {
                        "orders": {"resourceType": "model", "resourceName": "orders"}
                    },
                    "declaredColumnOrder": ["order_id"]
                }],
                "projections": [{
                    "templateIndex": 0,
                    "resourceNames": {"orders": "orders"}
                }]
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    assert_eq!(
        response["strings"],
        json!(["model", "orders", "order_id", "BIGINT"])
    );
    assert_eq!(response["facts"][0], json!([2, 3, 1, 0, 1, [[0, 1, 2]]]));
    assert_eq!(response["templates"][0], json!([[0], false]));
    assert_eq!(response["analyses"][0], json!([0, [[1, 1]]]));
    true
}

pub(crate) fn repeated_project_facts_intern_complete_facts() -> bool {
    let response: Value = serde_json::from_str(
        &analyze_project_compact_json(
            &json!({
                "queries": [{"sql": "SELECT 1 AS order_id", "dialect": "duckdb"}],
                "templates": [
                    {"queryIndex": 0},
                    {"queryIndex": 0}
                ],
                "projections": [
                    {"templateIndex": 0},
                    {"templateIndex": 1}
                ]
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    assert_eq!(response["facts"].as_array().map(Vec::len), Some(1));
    assert_eq!(response["templates"][0][0], json!([0]));
    assert_eq!(response["templates"][1][0], json!([0]));
    true
}

pub(crate) fn interleaved_query_templates_preserve_template_order() -> bool {
    let response: Value = serde_json::from_str(
        &analyze_project_compact_json(
            &json!({
                "queries": [
                    {"sql": "SELECT 1 AS first_value", "dialect": "duckdb"},
                    {"sql": "SELECT 2 AS second_value", "dialect": "duckdb"}
                ],
                "templates": [
                    {"queryIndex": 1},
                    {"queryIndex": 0},
                    {"queryIndex": 1}
                ],
                "projections": [
                    {"templateIndex": 0},
                    {"templateIndex": 1},
                    {"templateIndex": 2}
                ]
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    let strings = response["strings"]
        .as_array()
        .expect("compact strings should be an array");
    let facts = response["facts"]
        .as_array()
        .expect("compact facts should be an array");
    let templates = response["templates"]
        .as_array()
        .expect("compact templates should be an array");
    let names: Vec<&Value> = templates
        .iter()
        .map(|template| {
            let fact_index = template[0][0]
                .as_u64()
                .expect("template should use a fact index") as usize;
            let name_index = facts[fact_index][0]
                .as_u64()
                .expect("fact should use a name index") as usize;
            &strings[name_index]
        })
        .collect();
    names == vec!["second_value", "first_value", "second_value"]
}

pub(crate) fn canonical_queries_reuse_semantics_and_project_resources() -> bool {
    let response: Value = serde_json::from_str(
        &analyze_project_compact_json(
            &json!({
                "queries": [
                    {
                        "sql": "SELECT order_id FROM __sqlbuild_project_input_0",
                        "dialect": "duckdb",
                        "schema": {"tables": [{
                            "name": "__sqlbuild_project_input_0",
                            "columns": [{"name": "order_id", "type": "BIGINT", "nullable": false}]
                        }]}
                    }
                ],
                "templates": [{
                        "queryIndex": 0,
                        "references": {
                            "__sqlbuild_project_input_0": {
                                "resourceType": "model",
                                "resourceName": "__sqlbuild_project_input_0"
                            }
                        }
                }],
                "projections": [
                    {
                        "templateIndex": 0,
                        "resourceNames": {"__sqlbuild_project_input_0": "orders"}
                    },
                    {
                        "templateIndex": 0,
                        "resourceNames": {"__sqlbuild_project_input_0": "archived_orders"}
                    }
                ]
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");

    assert_eq!(response["uniqueQueryCount"], 1);
    assert_eq!(response["uniqueProjectionCount"], 1);
    assert_eq!(response["analyses"].as_array().map(Vec::len), Some(2));
    let strings = response["strings"]
        .as_array()
        .expect("compact strings should be an array");
    let fact_index = response["templates"][0][0][0]
        .as_u64()
        .expect("template should use a fact index") as usize;
    let canonical_resource_index = response["facts"][fact_index][5][0][1]
        .as_u64()
        .expect("canonical resource should use a string index")
        as usize;
    let first_resource_index = response["analyses"][0][1][0][1]
        .as_u64()
        .expect("first resource should use a string index") as usize;
    let second_resource_index = response["analyses"][1][1][0][1]
        .as_u64()
        .expect("second resource should use a string index")
        as usize;
    assert_eq!(
        strings[canonical_resource_index],
        "__sqlbuild_project_input_0"
    );
    assert_eq!(strings[first_resource_index], "orders");
    assert_eq!(strings[second_resource_index], "archived_orders");
    true
}
