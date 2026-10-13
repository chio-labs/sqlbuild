use crate::assembly::project::main::configured_namespace::configured_namespace;
use crate::assembly::project::tests::test_types::ConfiguredNamespaceTestCase;

#[test]
fn given_configured_value_when_reading_namespace_then_matches_python_strip() {
    let test_cases = [
        ConfiguredNamespaceTestCase {
            description: "surrounding whitespace is stripped",
            value: " \tanalytics\n",
            expected_namespace: Some("analytics"),
        },
        ConfiguredNamespaceTestCase {
            description: "a blank value names no namespace",
            value: " \u{3000}\u{1c} ",
            expected_namespace: None,
        },
        ConfiguredNamespaceTestCase {
            description: "an empty value names no namespace",
            value: "",
            expected_namespace: None,
        },
        ConfiguredNamespaceTestCase {
            description: "inner whitespace is kept",
            value: "\u{a0}sales data\u{2028}",
            expected_namespace: Some("sales data"),
        },
    ];

    for test_case in test_cases {
        let namespace = configured_namespace(test_case.value);

        assert_eq!(
            namespace.as_deref(),
            test_case.expected_namespace,
            "{}",
            test_case.description
        );
    }
}
