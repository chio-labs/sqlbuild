use crate::semantic_validation::tests::test_types::SemanticValidationTestCase;
use crate::semantic_validation::validation_json;

#[test]
fn given_unknown_column_when_validating_then_returns_structured_error() -> Result<(), String> {
    let test_cases = [SemanticValidationTestCase {
        description: "unknown column returns stable native evidence",
        request: r#"{
              "sql":"SELECT missing FROM upstream",
              "dialect":"generic",
              "schema":{"strict":true,"tables":[{"name":"upstream","columns":[{"name":"id","type":"INTEGER"}]}]},
              "options":{}
          }"#,
        expected_complete: true,
    }];
    for test_case in &test_cases {
        let response = validation_json(test_case.request)?;
        let observed_complete = ["\"valid\":false", "\"code\":\"E201\"", "missing"]
            .iter()
            .all(|expected| response.contains(expected));
        assert_eq!(
            observed_complete, test_case.expected_complete,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_valid_nested_clause_columns_when_validating_then_returns_no_errors() -> Result<(), String>
{
    let test_cases = [
        SemanticValidationTestCase {
            description: "QUALIFY accepts directly projected columns in a nested scope",
            request: r#"{
              "sql":"WITH prepared AS (SELECT customer_id, order_id FROM orders), selected AS (SELECT customer_id, order_id FROM prepared QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_id) = 1) SELECT order_id FROM selected",
              "dialect":"snowflake",
              "schema":{"strict":true,"tables":[{"name":"orders","columns":[{"name":"customer_id","type":"INTEGER"},{"name":"order_id","type":"INTEGER"}]}]},
              "options":{"check_references":true}
          }"#,
            expected_complete: true,
        },
        SemanticValidationTestCase {
            description: "JOIN USING compares resolved columns without case sensitivity",
            request: r#"{
              "sql":"WITH eligible AS (SELECT order_id FROM orders) SELECT orders.* FROM orders JOIN eligible USING (order_id)",
              "dialect":"snowflake",
              "schema":{"strict":true,"tables":[{"name":"orders","columns":[{"name":"ORDER_ID","type":"INTEGER"},{"name":"CUSTOMER_ID","type":"INTEGER"}]}]},
              "options":{"check_references":true}
          }"#,
            expected_complete: true,
        },
    ];
    for test_case in &test_cases {
        let response = validation_json(test_case.request)?;
        let observed_complete =
            response.contains("\"valid\":true") && response.contains("\"errors\":[]");
        assert_eq!(
            observed_complete, test_case.expected_complete,
            "{}: {response}",
            test_case.description
        );
    }
    Ok(())
}
