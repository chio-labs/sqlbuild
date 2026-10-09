use crate::semantic_checks::models::SemanticDeferral;
use crate::semantic_checks::tests::helpers::{expected_checked_outcome, metadata_outcome};
use crate::semantic_checks::tests::test_types::MetadataTestCase;

const MART_SHAPE: &[(&str, &str)] = &[
    ("order_id", "INTEGER"),
    ("scaled", "DOUBLE"),
    ("label", "VARCHAR"),
];

#[test]
fn given_project_metadata_when_checking_then_reports_python_errors_or_defers() {
    let test_cases = [
        MetadataTestCase {
            description: "function arity and families, config references, cursors and SQL tests",
            dialect: "duckdb",
            mart_shape: MART_SHAPE,
            expected_outcome: Ok(expected_checked_outcome()),
        },
        MetadataTestCase {
            description: "a dialect outside the native parser build",
            dialect: "mysql",
            mart_shape: MART_SHAPE,
            expected_outcome: Err(SemanticDeferral::UnsupportedDialect),
        },
        MetadataTestCase {
            description: "a column name Python case-folds beyond ASCII",
            dialect: "duckdb",
            mart_shape: &[("stra\u{df}e", "VARCHAR")],
            expected_outcome: Err(SemanticDeferral::NonAsciiText),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            metadata_outcome(&test_case),
            test_case.expected_outcome,
            "{}",
            test_case.description
        );
    }
}
