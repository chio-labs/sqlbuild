use crate::semantic_usage::analyze_json;
use crate::semantic_usage::tests::test_types::SemanticUsageTestCase;

#[test]
fn given_filter_and_join_when_analyzing_then_returns_direct_contextual_uses() -> Result<(), String>
{
    let test_cases = [SemanticUsageTestCase {
        description: "filter and join uses are complete",
        request: r#"{
            "sql":"SELECT o.id FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.active",
            "dialect":"generic",
            "schema":{"strict":true,"tables":[
              {"name":"orders","columns":[{"name":"id","type":"INTEGER"},{"name":"customer_id","type":"INTEGER"},{"name":"active","type":"BOOLEAN"}]},
              {"name":"customers","columns":[{"name":"id","type":"INTEGER"}]}
            ]}
          }"#,
        expected_complete: true,
    }];
    for test_case in &test_cases {
        let response = analyze_json(test_case.request)?;
        let observed_complete = [
            "\"context\":\"join_on\"",
            "\"context\":\"where\"",
            "\"column\":\"customer_id\"",
            "\"column\":\"active\"",
        ]
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
