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
