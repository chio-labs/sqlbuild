use std::time::{Duration, Instant};

use crate::compiler::main::model_header_errors::header_nesting_failure;
use crate::compiler::models::NestingFailure;
use crate::compiler::tests::helpers::{
    nested_header, nesting_error_at, parse_error_on_ordinary_thread,
};
use crate::compiler::tests::test_types::{HeaderNestingLocationTestCase, HeaderNestingTestCase};

const DEEP_HEADER_TIME_BOUND: Duration = Duration::from_secs(10);

#[test]
fn given_nested_header_values_when_parsing_on_an_ordinary_thread_then_depth_is_capped() {
    let test_cases = [
        HeaderNestingTestCase {
            description: "lists at the limit parse",
            prefix: "meta ",
            open: "[",
            close: "]",
            suffix: "",
            depth: 256,
            expected_error_position: None,
        },
        HeaderNestingTestCase {
            description: "lists one past the limit fail at the outermost extra list",
            prefix: "meta ",
            open: "[",
            close: "]",
            suffix: "",
            depth: 257,
            expected_error_position: Some(261),
        },
        HeaderNestingTestCase {
            description: "lists 1k deep",
            prefix: "meta ",
            open: "[",
            close: "]",
            suffix: "",
            depth: 1_000,
            expected_error_position: Some(261),
        },
        HeaderNestingTestCase {
            description: "lists 20k deep",
            prefix: "meta ",
            open: "[",
            close: "]",
            suffix: "",
            depth: 20_000,
            expected_error_position: Some(261),
        },
        HeaderNestingTestCase {
            description: "lists 100k deep",
            prefix: "meta ",
            open: "[",
            close: "]",
            suffix: "",
            depth: 100_000,
            expected_error_position: Some(261),
        },
        HeaderNestingTestCase {
            description: "sets 100k deep",
            prefix: "meta ",
            open: "{",
            close: "}",
            suffix: "",
            depth: 100_000,
            expected_error_position: Some(261),
        },
        HeaderNestingTestCase {
            description: "maps at the limit parse",
            prefix: "meta ",
            open: "(key ",
            close: ")",
            suffix: "",
            depth: 256,
            expected_error_position: None,
        },
        HeaderNestingTestCase {
            description: "maps 100k deep",
            prefix: "meta ",
            open: "(key ",
            close: ")",
            suffix: "",
            depth: 100_000,
            expected_error_position: Some(1_285),
        },
        HeaderNestingTestCase {
            description: "calls count their map and arguments, so 128 reach the limit",
            prefix: "meta ",
            open: "call(key ",
            close: ")",
            suffix: "",
            depth: 128,
            expected_error_position: None,
        },
        HeaderNestingTestCase {
            description: "calls one past the limit fail at the outermost extra call",
            prefix: "meta ",
            open: "call(key ",
            close: ")",
            suffix: "",
            depth: 129,
            expected_error_position: Some(1_157),
        },
        HeaderNestingTestCase {
            description: "calls 20k deep",
            prefix: "meta ",
            open: "call(key ",
            close: ")",
            suffix: "",
            depth: 20_000,
            expected_error_position: Some(1_157),
        },
        HeaderNestingTestCase {
            description: "typed constants 1k deep",
            prefix: "meta ",
            open: "constant(value ",
            close: ")",
            suffix: "",
            depth: 1_000,
            expected_error_position: Some(3_845),
        },
        HeaderNestingTestCase {
            description: "hook arguments 100k deep count the hook list, each hook and its arguments",
            prefix: "post_hooks [",
            open: "sql(\"refresh\", nested: ",
            close: ")",
            suffix: "]",
            depth: 100_000,
            expected_error_position: Some(2_933),
        },
    ];

    for test_case in test_cases {
        let started: Instant = Instant::now();

        let error: Option<String> = parse_error_on_ordinary_thread(nested_header(&test_case));

        assert_eq!(
            error,
            test_case.expected_error_position.map(nesting_error_at),
            "{}",
            test_case.description
        );
        assert!(
            started.elapsed() < DEEP_HEADER_TIME_BOUND,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_parse_errors_when_locating_nesting_failures_then_only_nesting_names_its_line() {
    let test_cases = [
        HeaderNestingLocationTestCase {
            description: "nesting error on the first header line",
            error: "values nest deeper than 256 levels at position 3",
            header: "a [[",
            header_line: 4,
            expected_failure: Some(NestingFailure {
                line: 4,
                message: "values nest deeper than 256 levels".to_owned(),
                help: "flatten the value so it nests at most 256 levels deep".to_owned(),
            }),
        },
        HeaderNestingLocationTestCase {
            description: "nesting error after non-ASCII text on later lines",
            error: "values nest deeper than 256 levels at position 12",
            header: "\n  é \"ü\",\n  [[",
            header_line: 2,
            expected_failure: Some(NestingFailure {
                line: 4,
                message: "values nest deeper than 256 levels".to_owned(),
                help: "flatten the value so it nests at most 256 levels deep".to_owned(),
            }),
        },
        HeaderNestingLocationTestCase {
            description: "other syntax errors are not nesting failures",
            error: "expected value at position 3",
            header: "a ]",
            header_line: 1,
            expected_failure: None,
        },
        HeaderNestingLocationTestCase {
            description: "a nesting prefix with an empty position is not a nesting failure",
            error: "values nest deeper than 256 levels at position ",
            header: "a [[",
            header_line: 1,
            expected_failure: None,
        },
        HeaderNestingLocationTestCase {
            description: "a nesting prefix without a position is not a nesting failure",
            error: "values nest deeper than 256 levels at position x",
            header: "a [[",
            header_line: 1,
            expected_failure: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            header_nesting_failure(test_case.error, test_case.header, test_case.header_line),
            test_case.expected_failure,
            "{}",
            test_case.description
        );
    }
}
