use serde_json::{Value, json};

#[test]
fn renders_ordered_comparison_batches() {
    let response: Value = serde_json::from_str(
        &super::main::render_json(
            &json!({
                "workers": 2,
                "requests": [{
                    "chain": [{
                        "modelName": "orders",
                        "resolvedSql": "SELECT 1 AS id",
                        "expectedCteSql": "SELECT 1 AS id"
                    }],
                    "assertions": [],
                    "sqlAnalysisEnabled": true,
                    "setDifferenceOperator": "EXCEPT",
                    "sqlAnalysisDialect": "duckdb"
                }]
            })
            .to_string(),
        )
        .unwrap(),
    )
    .unwrap();

    let sql = response[0]["sql"].as_str().unwrap();
    assert!(
        sql.contains("__actual__orders AS (SELECT 1 AS id)"),
        "{sql}"
    );
    assert!(sql.contains("__expected__orders AS (SELECT 1 AS id)"));
    assert!(sql.contains("EXCEPT"));
}
