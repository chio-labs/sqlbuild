//! Live destination evidence and history determine model migration precedence.

use crate::planner_migrations::main::model_decision::model_decision;
use crate::planner_migrations::tests::test_types::ModelDecisionTestCase;

#[test]
fn given_live_and_recorded_identity_when_deciding_then_preserves_replacement_precedence() {
    let test_cases = [
        ModelDecisionTestCase {
            description: "missing destination overrides stale history",
            destination_exists: false,
            history: (true, true, true),
            force: true,
            expected_decision: "migrate",
        },
        ModelDecisionTestCase {
            description: "reverse move supersedes even with force",
            destination_exists: true,
            history: (true, true, true),
            force: true,
            expected_decision: "superseded_replace",
        },
        ModelDecisionTestCase {
            description: "unrecorded destination redoes before force",
            destination_exists: true,
            history: (false, false, false),
            force: true,
            expected_decision: "redo",
        },
        ModelDecisionTestCase {
            description: "own history conflicts",
            destination_exists: true,
            history: (false, false, true),
            force: false,
            expected_decision: "conflict",
        },
        ModelDecisionTestCase {
            description: "force replaces own history",
            destination_exists: true,
            history: (false, false, true),
            force: true,
            expected_decision: "forced_replace",
        },
        ModelDecisionTestCase {
            description: "unrelated event prevents redo",
            destination_exists: true,
            history: (true, false, false),
            force: false,
            expected_decision: "conflict",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            model_decision(
                test_case.destination_exists,
                test_case.history,
                test_case.force
            ),
            test_case.expected_decision,
            "{}",
            test_case.description
        );
    }
}
