//! Decision precedence preserves live evidence across repeated and reversed renames.

use crate::planner_migrations::main::column_decision::column_decision;
use crate::planner_migrations::tests::test_types::ColumnDecisionTestCase;

#[test]
fn given_live_and_recorded_evidence_when_deciding_then_preserves_precedence() {
    let test_cases = [
        ColumnDecisionTestCase {
            description: "recorded destination wins over output",
            recorded: true,
            live: (true, true),
            still_produced: true,
            expected_decision: "done",
        },
        ColumnDecisionTestCase {
            description: "recorded missing origin is done",
            recorded: true,
            live: (false, false),
            still_produced: false,
            expected_decision: "done",
        },
        ColumnDecisionTestCase {
            description: "recreated origin must rename again",
            recorded: true,
            live: (true, false),
            still_produced: false,
            expected_decision: "rename",
        },
        ColumnDecisionTestCase {
            description: "still produced blocks rename",
            recorded: false,
            live: (true, false),
            still_produced: true,
            expected_decision: "still_produced",
        },
        ColumnDecisionTestCase {
            description: "missing original records existing destination",
            recorded: false,
            live: (false, true),
            still_produced: false,
            expected_decision: "record",
        },
        ColumnDecisionTestCase {
            description: "two live columns conflict",
            recorded: false,
            live: (true, true),
            still_produced: false,
            expected_decision: "conflict",
        },
        ColumnDecisionTestCase {
            description: "neither column is source missing",
            recorded: false,
            live: (false, false),
            still_produced: false,
            expected_decision: "source_missing",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            column_decision(test_case.recorded, test_case.live, test_case.still_produced),
            test_case.expected_decision,
            "{}",
            test_case.description
        );
    }
}
