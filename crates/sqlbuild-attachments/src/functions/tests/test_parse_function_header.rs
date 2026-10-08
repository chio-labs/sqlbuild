use crate::functions::main::parse_function_header::parse_function_header;
use crate::functions::models::{FunctionHeader, FunctionLanguage, FunctionReturns, HeaderValue};
use crate::functions::tests::helpers::{header, map, named, text};
use crate::functions::tests::test_types::FunctionHeaderTestCase;

#[test]
fn given_function_headers_when_parsing_then_python_values_or_deferrals_are_returned() {
    let test_cases = [
        FunctionHeaderTestCase {
            description: "a SQL table function with stripped arguments, columns and tags",
            header: header(&[
                ("arguments", map(&[(" raw_status ", text(" STRING "))])),
                (
                    "returns",
                    map(&[("table", map(&[("id", text("INTEGER"))]))]),
                ),
                ("tags", HeaderValue::Sequence(vec![text(" orders ")])),
                ("description", text(" Order rows. ")),
            ]),
            language: FunctionLanguage::Sql,
            expected_header: Some(FunctionHeader {
                arguments: vec![named(" raw_status ", "raw_status", "STRING")],
                returns: FunctionReturns::Table(vec![named("id", "id", "INTEGER")]),
                tags: vec!["orders".to_owned()],
                description: Some("Order rows.".to_owned()),
                runtime_version: None,
                entry_point: None,
                packages: Vec::new(),
            }),
        },
        FunctionHeaderTestCase {
            description: "a Python function with its runtime, entry point and packages",
            header: header(&[
                ("returns", text("STRING")),
                ("runtime_version", text("3.12")),
                ("entry_point", text(" label ")),
                ("packages", HeaderValue::Sequence(vec![text("numpy")])),
            ]),
            language: FunctionLanguage::Python,
            expected_header: Some(FunctionHeader {
                arguments: Vec::new(),
                returns: FunctionReturns::Type("STRING".to_owned()),
                tags: Vec::new(),
                description: None,
                runtime_version: Some("3.12".to_owned()),
                entry_point: Some("label".to_owned()),
                packages: vec!["numpy".to_owned()],
            }),
        },
        FunctionHeaderTestCase {
            description: "a missing return type defers so Python raises",
            header: header(&[("arguments", map(&[]))]),
            language: FunctionLanguage::Sql,
            expected_header: None,
        },
        FunctionHeaderTestCase {
            description: "a blank argument type defers so Python raises",
            header: header(&[
                ("returns", text("STRING")),
                ("arguments", map(&[("value", text("  "))])),
            ]),
            language: FunctionLanguage::Sql,
            expected_header: None,
        },
        FunctionHeaderTestCase {
            description: "a Python function returning a table defers so Python raises",
            header: header(&[
                (
                    "returns",
                    map(&[("table", map(&[("id", text("INTEGER"))]))]),
                ),
                ("runtime_version", text("3.12")),
                ("entry_point", text("label")),
            ]),
            language: FunctionLanguage::Python,
            expected_header: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            parse_function_header(&test_case.header, test_case.language),
            test_case.expected_header,
            "{}",
            test_case.description
        );
    }
}
