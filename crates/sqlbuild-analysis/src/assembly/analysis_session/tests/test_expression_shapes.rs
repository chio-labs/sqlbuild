use crate::assembly::analysis_session::main::expression_shapes::expression_shapes;
use crate::assembly::analysis_session::models::ExpressionShapeRequest;
use crate::assembly::analysis_session::tests::helpers::catalog;
use crate::assembly::analysis_session::tests::test_types::ExpressionShapeTestCase;

#[test]
fn given_source_expressions_when_inferring_shapes_then_matches_python_shapes() {
    let test_cases = [
        ExpressionShapeTestCase {
            description: "literal columns are typed",
            dialect: "duckdb",
            case_sensitive_shapes: false,
            expression: "(SELECT 1 AS order_id, 'placed' AS status)",
            expected_shape: r#"Inferred([("order_id", "INT"), ("status", "TEXT")])"#,
        },
        ExpressionShapeTestCase {
            description: "a star has no closed shape",
            dialect: "duckdb",
            case_sensitive_shapes: false,
            expression: "SELECT * FROM orders",
            expected_shape: "Absent",
        },
        ExpressionShapeTestCase {
            description: "unparseable SQL has no shape",
            dialect: "duckdb",
            case_sensitive_shapes: false,
            expression: "SELECT FROM WHERE",
            expected_shape: "Absent",
        },
        ExpressionShapeTestCase {
            description: "an unknown input column is UNKNOWN",
            dialect: "duckdb",
            case_sensitive_shapes: false,
            expression: "SELECT order_id + 1 AS next_id FROM orders",
            expected_shape: r#"Inferred([("next_id", "UNKNOWN")])"#,
        },
        ExpressionShapeTestCase {
            description: "case-insensitive dialects drop authored quoting",
            dialect: "duckdb",
            case_sensitive_shapes: false,
            expression: "SELECT 1 AS \"Mixed_Case\", CAST(2 AS BIGINT) AS total",
            expected_shape: r#"Inferred([("Mixed_Case", "INT"), ("total", "BIGINT")])"#,
        },
        ExpressionShapeTestCase {
            description: "case-sensitive dialects keep authored quoting",
            dialect: "postgresql",
            case_sensitive_shapes: true,
            expression: "SELECT 1 AS \"Mixed_Case\", CAST(2 AS BIGINT) AS total",
            expected_shape: r#"Inferred([("\"Mixed_Case\"", "INT"), ("total", "BIGINT")])"#,
        },
        ExpressionShapeTestCase {
            description: "untyped projections take Python's legacy analysis natively",
            dialect: "duckdb",
            case_sensitive_shapes: false,
            expression: "SELECT mystery_fn(1) AS event_id, NULL AS note",
            expected_shape: r#"Inferred([("event_id", "UNKNOWN"), ("note", "UNKNOWN")])"#,
        },
    ];
    for test_case in test_cases {
        let request = ExpressionShapeRequest {
            dialect: test_case.dialect.to_owned(),
            case_sensitive_shapes: test_case.case_sensitive_shapes,
            function_return_types: Vec::new(),
            nullability_rules: Some(Vec::new()),
            nullability_callback: None,
            expressions: vec![test_case.expression.to_owned()],
        };

        let shapes = expression_shapes(&catalog(test_case.dialect, &Vec::new()), &request)
            .expect("the batch runs");

        assert_eq!(
            format!("{shapes:?}"),
            format!("[{}]", test_case.expected_shape),
            "{}",
            test_case.description
        );
    }
}
