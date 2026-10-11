use crate::reference_markers::main::unresolved_reference_marker::unresolved_reference_marker;
use crate::reference_markers::tests::test_types::ReferenceMarkerTestCase;
use sqlbuild_sqltext::sql_scan::models::Unclosed;

#[test]
fn given_executable_sql_when_scanning_then_only_code_reference_calls_are_reported() {
    let test_cases = [
        ReferenceMarkerTestCase {
            description: "resolved SQL",
            sql: "SELECT * FROM orders",
            expected_marker: Ok(None),
        },
        ReferenceMarkerTestCase {
            description: "references in comments and strings are ignored",
            sql: "SELECT '__ref(x)' -- __seed(y)\n/* __source(z) */ FROM $q$__udf()$q$",
            expected_marker: Ok(None),
        },
        ReferenceMarkerTestCase {
            description: "a ref call outranks a later source call",
            sql: "SELECT * FROM __source(a) JOIN __ref(b)",
            expected_marker: Ok(Some(0)),
        },
        ReferenceMarkerTestCase {
            description: "a table function call",
            sql: "SELECT * FROM __table_fn(\"f\")",
            expected_marker: Ok(Some(4)),
        },
        ReferenceMarkerTestCase {
            description: "an unclosed quote while a marker is present",
            sql: "SELECT 'x FROM __ref(a)",
            expected_marker: Err(Unclosed::Quote),
        },
        ReferenceMarkerTestCase {
            description: "an unclosed quote without any marker is not scanned",
            sql: "SELECT 'x",
            expected_marker: Ok(None),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            unresolved_reference_marker(test_case.sql),
            test_case.expected_marker,
            "{}",
            test_case.description
        );
    }
}
