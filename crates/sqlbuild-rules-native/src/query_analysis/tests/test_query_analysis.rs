use crate::query_analysis::main::{
    analyze_json, analyze_project_compact_json, analyze_project_json,
};
use crate::query_analysis::tests::test_types::{QueryAnalysisExpectedValue, QueryAnalysisTestCase};
use serde_json::{Value, json};

#[test]
fn given_project_query_when_compact_analyzing_then_interns_repeated_lineage_strings() {
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
        .unwrap(),
    )
    .unwrap();

    assert_eq!(
        response["strings"],
        json!(["model", "orders", "order_id", "BIGINT"])
    );
    assert_eq!(response["facts"][0], json!([2, 3, 1, 0, 1, [[0, 1, 2]]]));
    assert_eq!(response["templates"][0], json!([[0], false]));
    assert_eq!(response["analyses"][0], json!([0, [[1, 1]]]));
}

#[test]
fn given_repeated_project_facts_when_compact_analyzing_then_interns_complete_facts() {
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
        .unwrap(),
    )
    .unwrap();

    assert_eq!(response["facts"].as_array().map(Vec::len), Some(1));
    assert_eq!(response["templates"][0][0], json!([0]));
    assert_eq!(response["templates"][1][0], json!([0]));
}

#[test]
fn given_canonical_queries_when_compact_analyzing_then_reuses_semantics_and_projects_resources() {
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
        .unwrap(),
    )
    .unwrap();

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
}

#[test]
fn given_query_analysis_cases_when_analyzing_batch_then_returns_expected_facts() {
    let test_cases = [
        QueryAnalysisTestCase {
            description: "raw batches preserve order and isolate parse errors",
            request: json!({
                "workers": 2,
                "requests": [
                    {"sql": "SELECT order_id FROM orders", "dialect": "duckdb"},
                    {"sql": "SELECT FROM", "dialect": "duckdb"},
                    {"sql": "SELECT product_id FROM products", "dialect": "duckdb"}
                ]
            }),
            analyze: analyze_json,
            expected_length: 3,
            expected_values: vec![
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/projections/0/name",
                    value: "order_id",
                },
                QueryAnalysisExpectedValue {
                    pointer: "/2/analysis/projections/0/name",
                    value: "product_id",
                },
            ],
            expected_nonempty_strings: vec!["/1/error"],
        },
        QueryAnalysisTestCase {
            description: "schema analysis returns typed nullable projections",
            request: json!({
                "requests": [{
                    "sql": "SELECT order_id FROM orders",
                    "dialect": "duckdb",
                    "schema": {"tables": [{
                        "name": "orders",
                        "columns": [{"name": "order_id", "type": "BIGINT", "nullable": false}]
                    }]}
                }]
            }),
            analyze: analyze_json,
            expected_length: 1,
            expected_values: vec![
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/projections/0/typeHint",
                    value: "BIGINT",
                },
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/projections/0/nullability",
                    value: "non_null",
                },
            ],
            expected_nonempty_strings: vec![],
        },
        QueryAnalysisTestCase {
            description: "project analysis returns compact lineage facts",
            request: json!({
                "requests": [{
                    "sql": "SELECT order_id FROM orders",
                    "dialect": "duckdb",
                    "schema": {"tables": [{
                        "name": "orders",
                        "columns": [{"name": "order_id", "type": "BIGINT", "nullable": false}]
                    }]},
                    "references": {
                        "orders": {"resourceType": "model", "resourceName": "orders"}
                    },
                    "declaredColumnOrder": ["order_id"]
                }]
            }),
            analyze: analyze_project_json,
            expected_length: 1,
            expected_values: vec![
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/columns/0/name",
                    value: "order_id",
                },
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/lineageColumns/0/upstreamColumns/0/resourceType",
                    value: "model",
                },
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/lineageColumns/0/upstreamColumns/0/resourceName",
                    value: "orders",
                },
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/lineageColumns/0/upstreamColumns/0/columnName",
                    value: "order_id",
                },
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/lineageColumns/0/confidence",
                    value: "high",
                },
            ],
            expected_nonempty_strings: vec![],
        },
        QueryAnalysisTestCase {
            description: "CTE recovery projects passthrough types",
            request: json!({
                "requests": [{
                    "sql": "WITH selected AS (SELECT CAST(order_id AS BIGINT) AS order_id FROM orders) SELECT order_id FROM selected",
                    "dialect": "duckdb",
                    "recoverCteFacts": true
                }]
            }),
            analyze: analyze_project_json,
            expected_length: 1,
            expected_values: vec![
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/columns/0/name",
                    value: "order_id",
                },
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/columns/0/type",
                    value: "BIGINT",
                },
            ],
            expected_nonempty_strings: vec![],
        },
        QueryAnalysisTestCase {
            description: "three-stage set operation CTEs preserve expression types",
            request: json!({
                "requests": [{
                    "sql": "WITH current_orders AS (SELECT CAST(status AS VARCHAR) AS status FROM orders), combined AS (SELECT status FROM current_orders UNION ALL SELECT CAST(NULL AS VARCHAR) AS status FROM orders), final AS (SELECT status FROM combined) SELECT status FROM final",
                    "dialect": "duckdb",
                    "schema": {"tables": [{
                        "name": "orders",
                        "columns": [{"name": "status", "type": "VARCHAR", "nullable": true}]
                    }]},
                    "recoverCteFacts": true
                }]
            }),
            analyze: analyze_project_json,
            expected_length: 1,
            expected_values: vec![QueryAnalysisExpectedValue {
                pointer: "/0/analysis/columns/0/type",
                value: "TEXT",
            }],
            expected_nonempty_strings: vec![],
        },
        QueryAnalysisTestCase {
            description: "typed set operation CTEs preserve all contract types",
            request: json!({
                "requests": [{
                    "sql": "WITH current_orders AS (SELECT CAST(category AS VARCHAR) AS category, id IN (1, 2) AS is_selected, TO_TIMESTAMP(0) AS processed_at, CAST(category AS VARCHAR) AS notes FROM upstream), combined AS (SELECT category, is_selected, processed_at, notes FROM current_orders -- Preserve archived records.\nUNION ALL SELECT category, TRUE AS is_selected, CAST(NULL AS TIMESTAMP) AS processed_at, NULL AS notes FROM upstream), final AS (SELECT category, is_selected, processed_at, notes FROM combined) SELECT category, is_selected, processed_at, notes FROM final",
                    "dialect": "snowflake",
                    "schema": {"tables": [{
                        "name": "upstream",
                        "columns": [
                            {"name": "id", "type": "INTEGER", "nullable": false},
                            {"name": "category", "type": "VARCHAR", "nullable": false}
                        ]
                    }]},
                    "functionReturnTypes": {"TO_TIMESTAMP": "TIMESTAMP_NTZ"},
                    "references": {
                        "upstream": {"resourceType": "model", "resourceName": "upstream"}
                    },
                    "recoverCteFacts": true
                }]
            }),
            analyze: analyze_project_json,
            expected_length: 1,
            expected_values: vec![
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/columns/0/type",
                    value: "TEXT",
                },
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/columns/1/type",
                    value: "BOOLEAN",
                },
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/columns/2/type",
                    value: "TIMESTAMP_NTZ",
                },
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/columns/3/type",
                    value: "TEXT",
                },
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/lineageColumns/0/upstreamColumns/0/resourceName",
                    value: "upstream",
                },
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/lineageColumns/0/upstreamColumns/0/columnName",
                    value: "category",
                },
            ],
            expected_nonempty_strings: vec![],
        },
        QueryAnalysisTestCase {
            description: "unbounded string casts preserve legacy type spelling",
            request: json!({
                "requests": [{
                    "sql": "SELECT CAST('new' AS VARCHAR) AS status",
                    "dialect": "duckdb"
                }]
            }),
            analyze: analyze_project_json,
            expected_length: 1,
            expected_values: vec![QueryAnalysisExpectedValue {
                pointer: "/0/analysis/columns/0/type",
                value: "TEXT",
            }],
            expected_nonempty_strings: vec![],
        },
        QueryAnalysisTestCase {
            description: "constant casts return compact canonical types",
            request: json!({
                "requests": [{
                    "sql": "SELECT CAST('new' AS VARCHAR(3)) AS status",
                    "dialect": "duckdb"
                }]
            }),
            analyze: analyze_project_json,
            expected_length: 1,
            expected_values: vec![
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/columns/0/type",
                    value: "VARCHAR(3)",
                },
                QueryAnalysisExpectedValue {
                    pointer: "/0/analysis/lineageColumns/0/transformKind",
                    value: "cast",
                },
            ],
            expected_nonempty_strings: vec![],
        },
        QueryAnalysisTestCase {
            description: "conjunctive non-null filters refine projected nullability",
            request: json!({
                "requests": [{
                    "sql": "SELECT o.order_id FROM orders o WHERE o.order_id IS NOT NULL",
                    "dialect": "duckdb",
                    "schema": {"tables": [{
                        "name": "orders",
                        "columns": [{"name": "order_id", "type": "INT", "nullable": true}]
                    }]},
                    "references": {
                        "orders": {"resourceType": "model", "resourceName": "orders"}
                    }
                }]
            }),
            analyze: analyze_project_json,
            expected_length: 1,
            expected_values: vec![QueryAnalysisExpectedValue {
                pointer: "/0/analysis/columns/0/nullability",
                value: "non_null",
            }],
            expected_nonempty_strings: vec![],
        },
    ];

    for test_case in test_cases {
        let response_json = (test_case.analyze)(&test_case.request.to_string())
            .expect("query analysis request should serialize");
        let response: Value =
            serde_json::from_str(&response_json).expect("query analysis response should be JSON");
        let responses = response
            .as_array()
            .expect("query analysis response should be an array");

        assert_eq!(
            responses.len(),
            test_case.expected_length,
            "{}",
            test_case.description
        );
        for expected_value in test_case.expected_values {
            assert_eq!(
                response
                    .pointer(expected_value.pointer)
                    .and_then(Value::as_str),
                Some(expected_value.value),
                "{}",
                test_case.description
            );
        }
        for expected_pointer in test_case.expected_nonempty_strings {
            assert!(
                response
                    .pointer(expected_pointer)
                    .and_then(Value::as_str)
                    .is_some_and(|value| !value.is_empty()),
                "{}",
                test_case.description
            );
        }
    }
}
