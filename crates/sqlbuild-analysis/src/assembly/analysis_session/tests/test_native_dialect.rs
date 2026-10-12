use crate::assembly::analysis_session::main::native_dialect::native_dialect;
use crate::assembly::analysis_session::tests::test_types::NativeDialectTestCase;

#[test]
fn given_analysis_dialect_when_resolving_native_dialect_then_matches_python_aliases() {
    let test_cases = [
        NativeDialectTestCase {
            description: "an aliased dialect maps to its polyglot name",
            dialect: Some("postgres"),
            expected_dialect: Some("postgresql"),
        },
        NativeDialectTestCase {
            description: "an unaliased dialect is kept",
            dialect: Some("snowflake"),
            expected_dialect: Some("snowflake"),
        },
        NativeDialectTestCase {
            description: "an empty dialect is kept",
            dialect: Some(""),
            expected_dialect: Some(""),
        },
        NativeDialectTestCase {
            description: "no dialect stays absent",
            dialect: None,
            expected_dialect: None,
        },
    ];

    for test_case in test_cases {
        let dialect = native_dialect(test_case.dialect);

        assert_eq!(
            dialect, test_case.expected_dialect,
            "{}",
            test_case.description
        );
    }
}
