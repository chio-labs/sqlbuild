use crate::functions::main::resolve_function_namespace::resolve_function_namespace;
use crate::functions::models::{FunctionLanguage, FunctionNamespace};
use crate::functions::tests::helpers::{namespace_inputs, owned};
use crate::functions::tests::test_types::FunctionNamespaceTestCase;

#[test]
fn given_function_namespaces_when_resolving_then_python_namespaces_are_returned() {
    let test_cases = [
        FunctionNamespaceTestCase {
            description: "SQL functions inherit the project defaults",
            inputs: namespace_inputs(FunctionLanguage::Sql, false),
            expected_namespace: FunctionNamespace {
                database: owned(Some("prod_db")),
                schema: owned(Some("udfs")),
                logical_database: owned(Some("analytics")),
                logical_schema: owned(Some("udfs")),
                fingerprint_database: owned(Some("prod_db")),
                fingerprint_schema: owned(Some("udfs")),
                fingerprint_logical_database: owned(Some("analytics")),
                fingerprint_logical_schema: owned(Some("udfs")),
            },
        },
        FunctionNamespaceTestCase {
            description: "Python functions that do not inherit keep only their own namespace",
            inputs: namespace_inputs(FunctionLanguage::Python, false),
            expected_namespace: FunctionNamespace {
                database: None,
                schema: owned(Some("udfs")),
                logical_database: None,
                logical_schema: owned(Some("udfs")),
                fingerprint_database: owned(Some("prod_db")),
                fingerprint_schema: owned(Some("udfs")),
                fingerprint_logical_database: owned(Some("analytics")),
                fingerprint_logical_schema: owned(Some("udfs")),
            },
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            resolve_function_namespace(&test_case.inputs),
            test_case.expected_namespace,
            "{}",
            test_case.description
        );
    }
}
