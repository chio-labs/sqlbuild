use crate::execution_limits::main::parse_execution_limit::parse_execution_limit;
use crate::execution_limits::models::ExecutionLimit;
use crate::execution_limits::tests::test_types::ParseExecutionLimitTestCase;

#[test]
fn given_limit_text_when_parsing_then_expected_limit_is_returned() {
    let test_cases = [
        ParseExecutionLimitTestCase {
            description: "seconds",
            text: "30s",
            expected_limit: Some(ExecutionLimit::Seconds(30)),
        },
        ParseExecutionLimitTestCase {
            description: "compound fixed duration",
            text: "1h30m",
            expected_limit: Some(ExecutionLimit::Seconds(5_400)),
        },
        ParseExecutionLimitTestCase {
            description: "disabled",
            text: "disabled",
            expected_limit: Some(ExecutionLimit::Disabled),
        },
        ParseExecutionLimitTestCase {
            description: "calendar duration",
            text: "1mo",
            expected_limit: None,
        },
        ParseExecutionLimitTestCase {
            description: "zero",
            text: "0s",
            expected_limit: None,
        },
        ParseExecutionLimitTestCase {
            description: "bare number",
            text: "30",
            expected_limit: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            parse_execution_limit(test_case.text),
            test_case.expected_limit,
            "{}",
            test_case.description
        );
    }
}
