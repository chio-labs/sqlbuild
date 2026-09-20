use serde_json::{Value, json};

#[test]
fn plans_and_renders_model_test_batch() {
    let response: Value = serde_json::from_str(
        &super::main::plan_and_render_json(
            &json!({
                "models": [
                    {
                        "name": "stg_orders",
                        "querySql": "SELECT * FROM __source(\"raw_orders\")",
                        "modelDependencies": []
                    },
                    {
                        "name": "orders",
                        "querySql": "SELECT * FROM __ref(\"stg_orders\")",
                        "modelDependencies": ["stg_orders"]
                    }
                ],
                "functions": [],
                "tests": [{
                    "name": "orders_case",
                    "fileLabel": "tests/orders.sql",
                    "payload": {
                        "kind": "model",
                        "authoredCtes": [{
                            "name": "__source__raw_orders",
                            "sqlBody": "SELECT 1 AS order_id"
                        }],
                        "expectedCtes": [{
                            "name": "__expected__orders",
                            "sqlBody": "SELECT 1 AS order_id"
                        }],
                        "expectedModelNames": ["orders"],
                        "assertionCtes": []
                    }
                }],
                "sqlAnalysisEnabled": true,
                "sqlAnalysisDialect": "duckdb",
                "setDifferenceOperator": "EXCEPT",
                "workers": 2
            })
            .to_string(),
        )
        .unwrap(),
    )
    .unwrap();

    assert_eq!(
        response["artifacts"][0]["modelNames"],
        json!(["stg_orders", "orders"])
    );
    let sql = response["artifacts"][0]["sql"].as_str().unwrap();
    assert!(sql.contains("__source__raw_orders AS (SELECT 1 AS order_id)"));
    assert!(sql.contains("__ref__stg_orders AS"));
    assert!(sql.contains("__actual__orders AS"));
    assert!(sql.contains("__expected__orders AS"));
    assert_eq!(response["artifacts"][0]["warnings"], json!([]));
    assert!(response["planningNs"].as_u64().is_some());
    assert!(response["renderingNs"].as_u64().is_some());
}

#[test]
fn preserves_unicode_cte_identifiers_after_leading_with() {
    let response: Value = serde_json::from_str(
        &super::main::plan_and_render_json(
            &json!({
                "models": [{
                    "name": "orders",
                    "querySql": "WITH \"订单行\" AS (SELECT order_id FROM __source(\"raw_orders\")) SELECT order_id FROM \"订单行\"",
                    "modelDependencies": []
                }],
                "functions": [],
                "tests": [{
                    "name": "orders_case",
                    "fileLabel": "tests/orders.sql",
                    "payload": {
                        "kind": "model",
                        "authoredCtes": [{
                            "name": "__source__raw_orders",
                            "sqlBody": "SELECT 1 AS order_id"
                        }],
                        "expectedCtes": [{
                            "name": "__expected__orders",
                            "sqlBody": "SELECT 1 AS order_id"
                        }],
                        "expectedModelNames": ["orders"],
                        "assertionCtes": []
                    }
                }],
                "sqlAnalysisEnabled": true,
                "sqlAnalysisDialect": "duckdb"
            })
            .to_string(),
        )
        .unwrap(),
    )
    .unwrap();

    let sql = response["artifacts"][0]["sql"].as_str().unwrap();
    assert!(sql.contains("WITH __source__raw_orders AS"));
    assert!(sql.contains("订单行"), "{sql}");
}
