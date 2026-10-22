use crate::dispatch::main::closing_status::closing_status;
use crate::dispatch::tests::test_types::ClosingStatusTestCase;

#[test]
fn given_command_outcome_when_closing_a_notice_then_the_outcome_is_the_last_line() {
    let test_cases = [
        ClosingStatusTestCase {
            description: "success names the only affected output",
            exit_code: Some(0),
            affected: Some("lifecycle event export"),
            expected_status: "sqb audit completed successfully; only its lifecycle event export \
                              is affected.\n",
        },
        ClosingStatusTestCase {
            description: "failure reports the exit code",
            exit_code: Some(2),
            affected: Some("lifecycle event export"),
            expected_status: "sqb audit failed with exit code 2.\n",
        },
        ClosingStatusTestCase {
            description: "unknown exit code reports failure",
            exit_code: None,
            affected: Some("lifecycle event export"),
            expected_status: "sqb audit failed.\n",
        },
        ClosingStatusTestCase {
            description: "success after an informational notice names nothing affected",
            exit_code: Some(0),
            affected: None,
            expected_status: "sqb audit completed successfully.\n",
        },
        ClosingStatusTestCase {
            description: "failure after an informational notice still reports the exit code",
            exit_code: Some(1),
            affected: None,
            expected_status: "sqb audit failed with exit code 1.\n",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            closing_status("audit", test_case.exit_code, test_case.affected),
            test_case.expected_status,
            "{}",
            test_case.description
        );
    }
}
