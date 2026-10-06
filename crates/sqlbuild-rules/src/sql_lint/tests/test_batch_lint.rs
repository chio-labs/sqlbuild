use crate::sql_lint::main::batch_engine::lint_batch_json;
use crate::sql_lint::main::engine::lint_json;
use crate::sql_lint::tests::test_types::BatchLintTestCase;
use serde_json::{Value, json};

#[test]
fn given_mixed_lint_inputs_when_batching_then_preserves_order_errors_and_findings() {
    let test_cases = [BatchLintTestCase {
        description: "mixed valid and invalid SQL retains standalone evidence",
        queries: &[
            "SELECT 1",
            "SELECT FROM",
            "SELECT order_id FROM orders WHERE order_id = NULL",
        ],
        expected_responses: 3,
    }];
    for test_case in test_cases {
        let requests: Vec<Value> = test_case
            .queries
            .iter()
            .map(|sql| json!({"version": 1, "sql": sql, "dialect": "duckdb"}))
            .collect();
        let expected: Vec<Value> = requests
            .iter()
            .map(|request| {
                serde_json::to_value(lint_json(&request.to_string()).map(|response| {
                    serde_json::from_str::<Value>(&response).expect("valid response")
                }))
                .expect("serializable result")
            })
            .collect();
        let response = lint_batch_json(&serde_json::to_string(&requests).expect("valid requests"))
            .expect("valid batch");
        let actual: Vec<Value> = serde_json::from_str(&response).expect("valid response");
        assert_eq!(
            actual.len(),
            test_case.expected_responses,
            "{}",
            test_case.description
        );
        assert_eq!(actual, expected, "{}", test_case.description);
    }
}
