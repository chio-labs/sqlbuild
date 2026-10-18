use serde_json::{Value, json};

fn render_single(request: Value) -> String {
    let response: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_rendering::render_json(
            &json!({"requests": [request]}).to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");
    response[0]["sql"]
        .as_str()
        .expect("test assumption must hold")
        .to_string()
}

fn lifted_step() -> Value {
    json!({
        "modelName": "orders",
        "resolvedSql": "WITH __ref__stg_orders AS (SELECT 1 AS order_id) SELECT * FROM __ref__stg_orders",
        "expectedCteSql": "SELECT 2 AS order_id",
        "liftedCtes": [["__ref__stg_orders", "SELECT 1 AS order_id"]],
        "comparisonBodySql": "SELECT * FROM __ref__stg_orders"
    })
}

pub(crate) fn stored_actual_output_is_read_instead_of_the_chain() -> bool {
    let output = render_single(json!({
        "chain": [lifted_step()],
        "sqlAnalysisEnabled": false,
        "sqlAnalysisDialect": "duckdb",
        "outputStepIndex": 0
    }));
    assert!(
        output.ends_with("\nSELECT * FROM __actual__orders"),
        "{output}"
    );
    assert!(
        output.contains("__ref__stg_orders AS (SELECT 1 AS order_id)"),
        "{output}"
    );
    assert!(!output.contains("__expected__orders"), "{output}");

    let comparison = render_single(json!({
        "chain": [lifted_step()],
        "sqlAnalysisEnabled": false,
        "sqlAnalysisDialect": "duckdb",
        "actualRelations": {"0": "stored_orders"}
    }));
    assert!(
        comparison.contains("__actual__orders AS (SELECT * FROM stored_orders)"),
        "{comparison}"
    );
    assert!(!comparison.contains("__ref__stg_orders"), "{comparison}");
    assert!(comparison.contains("AS unexpected_count"), "{comparison}");

    let sample: Value = serde_json::from_str(
        &crate::compiler::main::sql_test_difference_sampling::render_difference_sample_json(
            &json!({
                "step": lifted_step(),
                "sqlAnalysisEnabled": false,
                "setDifferenceOperator": "EXCEPT",
                "sqlAnalysisDialect": "duckdb",
                "direction": "missing",
                "sampleLimit": 3,
                "actualRelation": "stored_orders"
            })
            .to_string(),
        )
        .expect("test assumption must hold"),
    )
    .expect("test assumption must hold");
    let sample_sql = sample["sql"].as_str().expect("test assumption must hold");
    assert!(
        sample_sql.contains("__actual AS (SELECT * FROM stored_orders)"),
        "{sample_sql}"
    );
    assert!(!sample_sql.contains("__ref__stg_orders"), "{sample_sql}");
    true
}
