//! Source calls and deferral templates follow Python's regular expression semantics.

use crate::planner_warehouse::main::source_call_names::source_call_names;
use crate::planner_warehouse::main::source_deferral_field::source_deferral_field;
use crate::planner_warehouse::tests::test_types::{DeferralFieldTestCase, SourceCallTestCase};

#[test]
fn given_sql_when_scanning_source_calls_then_returns_quoted_names_in_order() {
    let test_cases = [
        SourceCallTestCase {
            description: "two calls",
            sql: r#"SELECT * FROM __source("orders") JOIN __source("customers")"#,
            expected_names: vec!["orders", "customers"],
        },
        SourceCallTestCase {
            description: "unterminated and empty calls are skipped",
            sql: r#"__source("") __source("a" x) __source("b")"#,
            expected_names: vec!["b"],
        },
        SourceCallTestCase {
            description: "no calls",
            sql: "SELECT 1",
            expected_names: Vec::new(),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            source_call_names(test_case.sql),
            test_case.expected_names,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_target_template_when_resolving_then_substitutes_context_and_known_variables() {
    let test_cases = [
        DeferralFieldTestCase {
            description: "absent target keeps logical value",
            target_value: None,
            logical_value: Some("raw"),
            expected_value: Some("raw"),
        },
        DeferralFieldTestCase {
            description: "context and variables substitute",
            target_value: Some("${CTX:schema}_${env}_${missing}_${CTX:other}"),
            logical_value: Some("raw"),
            expected_value: Some("raw_prod_${missing}_${CTX:other}"),
        },
        DeferralFieldTestCase {
            description: "variable with colon is retried at the next character",
            target_value: Some("${a:${env}}"),
            logical_value: None,
            expected_value: Some("${a:prod}"),
        },
    ];
    for test_case in test_cases {
        let resolved = source_deferral_field(
            (test_case.target_value, test_case.logical_value),
            |name: &str| Ok::<_, ()>((name == "env").then(|| "prod".to_owned())),
        );
        assert_eq!(
            resolved,
            Ok(test_case.expected_value.map(str::to_owned)),
            "{}",
            test_case.description
        );
    }
}
