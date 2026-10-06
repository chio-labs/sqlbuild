use crate::models::{DeclarationKind, Diagnostic, DiagnosticSeverity, SqlValue};
use crate::tests::helpers::{declaration, diagnostic, list_of_integer_sets, private_constant};
use crate::tests::test_types::{
    DiagnosticOrderTestCase, IdentityOrderTestCase, IdentityTextTestCase, SqlTypeNameTestCase,
};

#[test]
fn given_identities_when_formatting_then_text_matches_python_format_identity() {
    let test_cases = [
        IdentityTextTestCase {
            description: "public declaration",
            identity: declaration(DeclarationKind::SqlHook, "grant_reader"),
            expected_text: "sql_hook:grant_reader",
        },
        IdentityTextTestCase {
            description: "private declaration names its owner",
            identity: private_constant("staging.orders", "status"),
            expected_text: "constant:model:staging.orders.status",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            test_case.identity.to_string(),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_identities_when_sorting_then_order_follows_python_enum_values() {
    let test_cases = [IdentityOrderTestCase {
        description: "kinds compare by their string values, then names, then owners",
        identities: vec![
            declaration(DeclarationKind::Schema, "a"),
            private_constant("orders", "b"),
            declaration(DeclarationKind::Macro, "a"),
            declaration(DeclarationKind::Constant, "b"),
            declaration(DeclarationKind::Audit, "z"),
        ],
        expected_texts: vec![
            "audit:z",
            "constant:b",
            "constant:model:orders.b",
            "macro:a",
            "schema:a",
        ],
    }];
    for test_case in test_cases {
        let mut identities = test_case.identities;
        identities.sort();
        let texts: Vec<String> = identities.iter().map(ToString::to_string).collect();
        assert_eq!(texts, test_case.expected_texts, "{}", test_case.description);
    }
}

#[test]
fn given_diagnostics_from_parallel_work_when_sorting_by_order_key_then_serial_order_returns() {
    let test_cases = [DiagnosticOrderTestCase {
        description: "resource order, then stage, then sequence",
        diagnostics: vec![
            diagnostic("C003", DiagnosticSeverity::Warning, [1, 0, 0]),
            diagnostic("C002", DiagnosticSeverity::Error, [0, 1, 0]),
            diagnostic("C001", DiagnosticSeverity::Info, [0, 0, 1]),
            diagnostic("C000", DiagnosticSeverity::Error, [0, 0, 0]),
        ],
        expected_codes: vec!["C000", "C001", "C002", "C003"],
        expected_errors: vec![true, false, true, false],
    }];
    for test_case in test_cases {
        let mut diagnostics = test_case.diagnostics;
        diagnostics.sort_by_key(|item| item.order_key);
        let codes: Vec<&str> = diagnostics.iter().map(|item| item.code.as_str()).collect();
        let errors: Vec<bool> = diagnostics.iter().map(Diagnostic::is_error).collect();
        assert_eq!(codes, test_case.expected_codes, "{}", test_case.description);
        assert_eq!(
            errors, test_case.expected_errors,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_typed_values_when_naming_types_then_names_match_python_display_name() {
    let test_cases = [
        SqlTypeNameTestCase {
            description: "nested collections name every element type",
            value: list_of_integer_sets(),
            expected_name: "list<set<integer>>",
        },
        SqlTypeNameTestCase {
            description: "scalar",
            value: SqlValue::Float(1.5),
            expected_name: "float",
        },
        SqlTypeNameTestCase {
            description: "object has no element type",
            value: SqlValue::Object(vec![("status".to_owned(), SqlValue::Null)]),
            expected_name: "object",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            test_case.value.logical_type().display_name(),
            test_case.expected_name,
            "{}",
            test_case.description
        );
    }
}
