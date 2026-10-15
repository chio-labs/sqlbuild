use crate::lifecycle_events::main::validate_known_event::validate_known_event;
use crate::lifecycle_events::tests::helpers::{event, int, text};
use crate::lifecycle_events::tests::test_types::ValidateTestCase;

#[test]
fn given_lifecycle_event_when_validating_then_first_contract_violation_is_reported() {
    let test_cases = [
        ValidateTestCase {
            description: "unknown type",
            event: event("custom", Vec::new()),
            expected_result: Err(
                "unknown lifecycle event_type 'custom'; decode it as an opaque envelope",
            ),
        },
        ValidateTestCase {
            description: "unexpected payload lists allowed fields",
            event: event("invocation_started", vec![("x", int(1))]),
            expected_result: Err(
                "payload field(s) not allowed for known event 'invocation_started': x; allowed fields: command",
            ),
        },
        ValidateTestCase {
            description: "retry numbering",
            event: event(
                "retry_scheduled",
                vec![
                    ("failed_attempt_number", int(1)),
                    ("next_attempt_number", int(3)),
                    ("delay_ms", int(5)),
                    ("error_type", text("E")),
                ],
            ),
            expected_result: Err("next_attempt_number must equal failed_attempt_number + 1"),
        },
        ValidateTestCase {
            description: "uncatalogued operation adapter",
            event: event("operation_started", vec![("adapter", text("other"))]),
            expected_result: Err("adapter must be a catalogued value"),
        },
        ValidateTestCase {
            description: "valid run start",
            event: event(
                "run_started",
                vec![
                    ("configured_concurrency", int(4)),
                    ("selected_count", int(2)),
                    ("worker_count", int(2)),
                ],
            ),
            expected_result: Ok(()),
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            validate_known_event(&test_case.event),
            test_case.expected_result.map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
