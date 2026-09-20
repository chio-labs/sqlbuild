use super::main::extract_batch_json;

#[test]
fn given_mixed_expanded_tests_when_extracting_batch_then_order_and_payloads_are_preserved() {
    let response = extract_batch_json(r#"{"tests":[{"sql":"WITH helper AS (SELECT 1 AS id), __source__raw_orders AS (SELECT id FROM helper), __expected__orders AS (SELECT id FROM helper), __assert__positive AS (SELECT id FROM helper WHERE id < 0) SELECT 1","fileLabel":"tests/orders.sql","mode":"model"},{"sql":"WITH input AS (SELECT 1 AS value), __udf_actual__ AS (SELECT __udf(\"increment\")(value) AS value FROM input), __udf_expected__ AS (SELECT 2 AS value) SELECT 1","fileLabel":"tests/increment.sql","mode":"udf"}]}"#).expect("batch succeeds");
    let payload: serde_json::Value = serde_json::from_str(&response).expect("valid JSON");
    assert_eq!(payload[0]["kind"], "model");
    assert_eq!(payload[0]["authored"][0][0], "helper");
    assert_eq!(payload[0]["expectedModels"][0], "orders");
    assert_eq!(payload[0]["assertionNames"][0], "positive");
    assert_eq!(payload[1]["kind"], "direct");
    assert_eq!(payload[1]["mode"], "udf");
    assert_eq!(payload[1]["actual"][0], "__udf_actual__");
}

#[test]
fn given_dependent_assertion_when_extracting_batch_then_authoritative_error_is_returned() {
    let error = extract_batch_json(r#"{"tests":[{"sql":"WITH __source__raw_orders AS (SELECT 1 AS id), __expected__orders AS (SELECT 1 AS id), __assert__same AS (SELECT id FROM __expected__orders) SELECT 1","fileLabel":"tests/orders.sql","mode":"model"}]}"#).expect_err("dependency is rejected");
    assert!(error.contains("'__assert__same' must not depend on '__expected__orders'"));
}

#[test]
fn given_quoted_ctes_and_implicit_alias_when_extracting_then_supported_payload_is_preserved() {
    let response = extract_batch_json(r#"{"tests":[{"sql":"WITH \"__source__raw_orders\" AS (SELECT 1 AS id), \"__expected__orders\" AS (SELECT CAST(1 AS INTEGER) id) SELECT 1","fileLabel":"tests/orders.sql","mode":"model"}]}"#).expect("batch succeeds");
    let payload: serde_json::Value = serde_json::from_str(&response).expect("valid JSON");
    assert_eq!(payload[0]["authored"][0][0], "__source__raw_orders");
    assert_eq!(payload[0]["expected"][0][1], "SELECT CAST(1 AS INTEGER) id");
}
