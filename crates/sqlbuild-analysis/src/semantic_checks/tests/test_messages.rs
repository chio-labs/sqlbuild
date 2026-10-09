use crate::semantic_checks::_helpers::explanation::messages::comparison_help;
use crate::semantic_checks::models::SemanticDeferral;
use crate::semantic_checks::tests::helpers::{missing_parts, owned_missing, sentence};
use crate::semantic_checks::tests::test_types::{ComparisonHelpTestCase, SentenceMessageTestCase};

#[test]
fn given_binding_messages_when_rewriting_then_matches_python_sentences() {
    let test_cases = [
        SentenceMessageTestCase {
            description: "a context suffix and unquoted type words",
            message: "Binary operator types integer and timestamp are incompatible (context: x > 5)",
            expected_sentence: Ok("BINARY operator types INTEGER and TIMESTAMP are incompatible"),
            expected_missing: Ok(None),
        },
        SentenceMessageTestCase {
            description: "quoted type words stay as written",
            message: "Cannot compare 'varchar' with date values",
            expected_sentence: Ok("Cannot compare 'varchar' with DATE values"),
            expected_missing: Ok(None),
        },
        SentenceMessageTestCase {
            description: "an unknown column in a named table",
            message: "Unknown column 'amonut' in table 'raw_orders'",
            expected_sentence: Ok("Unknown column 'amonut' in table 'raw_orders'"),
            expected_missing: Ok(Some(("amonut", Some("raw_orders")))),
        },
        SentenceMessageTestCase {
            description: "an unknown column without a table",
            message: "Unknown column 'amonut'",
            expected_sentence: Ok("Unknown column 'amonut'"),
            expected_missing: Ok(Some(("amonut", None))),
        },
        SentenceMessageTestCase {
            description: "a non-ASCII column Python's regex classes read differently",
            message: "Unknown column 'stra\u{df}e'",
            expected_sentence: Err(SemanticDeferral::NonAsciiText),
            expected_missing: Err(SemanticDeferral::NonAsciiText),
        },
        SentenceMessageTestCase {
            description: "a line break Python's end anchor treats specially",
            message: "Unknown column 'a'\nin table 'b'",
            expected_sentence: Err(SemanticDeferral::NonAsciiText),
            expected_missing: Err(SemanticDeferral::NonAsciiText),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            sentence(test_case.message),
            test_case.expected_sentence.map(str::to_owned),
            "{}",
            test_case.description
        );
        assert_eq!(
            missing_parts(test_case.message),
            owned_missing(test_case.expected_missing),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_comparison_types_when_building_help_then_offers_python_literals() {
    let test_cases = [
        ComparisonHelpTestCase {
            description: "a timestamp on BigQuery",
            types: &["TIMESTAMP", "INTEGER"],
            dialect: Some("bigquery"),
            expected_help: "compare with a timestamp, for example TIMESTAMP '2026-04-01 00:00:00+00'",
        },
        ComparisonHelpTestCase {
            description: "a timestamp elsewhere",
            types: &["INTEGER", "TIMESTAMP WITH TIME ZONE"],
            dialect: Some("duckdb"),
            expected_help: "compare with a timestamp, for example TIMESTAMP '2026-04-01'",
        },
        ComparisonHelpTestCase {
            description: "a date",
            types: &["DATE"],
            dialect: None,
            expected_help: "compare with a date, for example DATE '2026-04-01'",
        },
        ComparisonHelpTestCase {
            description: "no temporal type",
            types: &["INTEGER", "VARCHAR"],
            dialect: None,
            expected_help: "compare compatible types using a correctly typed literal or explicit conversion",
        },
    ];
    for test_case in test_cases {
        let types: Vec<String> = test_case
            .types
            .iter()
            .map(|value| (*value).to_owned())
            .collect();
        assert_eq!(
            comparison_help(&types, test_case.dialect),
            test_case.expected_help,
            "{}",
            test_case.description
        );
    }
}
