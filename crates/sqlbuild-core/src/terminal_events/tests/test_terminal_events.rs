use crate::terminal_events::main::claim_resource_terminal::claim_resource_terminal;
use crate::terminal_events::main::consume_terminal_fact::consume_terminal_fact;
use crate::terminal_events::main::latest_resource_terminal::latest_resource_terminal;
use crate::terminal_events::main::lifecycle_terminal::lifecycle_terminal;
use crate::terminal_events::models::{TerminalFact, TerminalIndex, TerminalRequest};
use crate::terminal_events::tests::helpers::{attempt, fact, orders_request};
use crate::terminal_events::tests::test_types::{ClaimTestCase, LifecycleTestCase};

#[test]
fn given_resource_terminals_when_claiming_then_each_attempt_is_claimed_once() {
    let test_cases = [
        ClaimTestCase {
            description: "a duplicate event is retained once and claimed once",
            facts: vec![
                attempt("e1", "resource_attempt_completed", ("a1", 1)),
                attempt("e1", "resource_attempt_completed", ("a1", 1)),
            ],
            requests: vec![orders_request(), orders_request()],
            expected_claims: vec![Some(0), None],
            expected_latest: Some(0),
        },
        ClaimTestCase {
            description: "claiming the latest attempt retires the earlier one",
            facts: vec![
                attempt("e1", "resource_attempt_failed", ("a1", 1)),
                fact("r1", "run_started"),
                attempt("e2", "resource_attempt_completed", ("a2", 2)),
            ],
            requests: vec![orders_request(), orders_request()],
            expected_claims: vec![Some(2), None],
            expected_latest: Some(2),
        },
        ClaimTestCase {
            description: "an attempt number selects an earlier attempt",
            facts: vec![
                attempt("e1", "resource_attempt_failed", ("a1", 1)),
                attempt("e2", "resource_attempt_completed", ("a2", 2)),
            ],
            requests: vec![
                TerminalRequest {
                    attempt_number: Some(1),
                    ..orders_request()
                },
                TerminalRequest {
                    resource_attempt_id: Some("a2".to_owned()),
                    resource_id: Some("model:orders".to_owned()),
                    ..orders_request()
                },
            ],
            expected_claims: vec![Some(0), Some(1)],
            expected_latest: Some(1),
        },
        ClaimTestCase {
            description: "a name seen under two identifiers needs an explicit identifier",
            facts: vec![
                attempt("e1", "resource_attempt_completed", ("a1", 1)),
                TerminalFact {
                    resource_id: Some("seed:orders".to_owned()),
                    ..attempt("e2", "resource_attempt_completed", ("a2", 1))
                },
            ],
            requests: vec![orders_request()],
            expected_claims: vec![None],
            expected_latest: None,
        },
    ];

    for test_case in test_cases {
        let mut index: TerminalIndex = TerminalIndex::default();
        for fact in test_case.facts {
            index = consume_terminal_fact(index, fact).0;
        }
        let mut claims: Vec<Option<usize>> = Vec::new();
        for request in &test_case.requests {
            let (claimed, claim) = claim_resource_terminal(index, request);
            index = claimed;
            claims.push(claim);
        }
        assert_eq!(
            (claims, latest_resource_terminal(&index, "orders", None)),
            (test_case.expected_claims, test_case.expected_latest),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_lifecycle_facts_when_selecting_terminal_then_strongest_wins() {
    let test_cases = [
        LifecycleTestCase {
            description: "a failed resource outranks a later completed resource",
            facts: vec![
                attempt("e1", "resource_attempt_failed", ("a1", 1)),
                attempt("e2", "resource_attempt_completed", ("a2", 2)),
            ],
            expected_terminal: Some(0),
        },
        LifecycleTestCase {
            description: "a run terminal outranks resources and non-aggregate operations",
            facts: vec![
                fact("r1", "run_completed"),
                fact("o1", "operation_failed"),
                attempt("e1", "resource_attempt_failed", ("a1", 1)),
            ],
            expected_terminal: Some(0),
        },
        LifecycleTestCase {
            description: "an aggregate operation terminal outranks a failed resource",
            facts: vec![
                TerminalFact {
                    operation_name: Some("clone_execution".to_owned()),
                    ..fact("o1", "operation_completed")
                },
                attempt("e1", "resource_attempt_failed", ("a1", 1)),
            ],
            expected_terminal: Some(0),
        },
        LifecycleTestCase {
            description: "no terminal facts",
            facts: vec![fact("r1", "run_started")],
            expected_terminal: None,
        },
    ];

    for test_case in test_cases {
        let mut index: TerminalIndex = TerminalIndex::default();
        for fact in test_case.facts {
            index = consume_terminal_fact(index, fact).0;
        }
        assert_eq!(
            lifecycle_terminal(&index),
            test_case.expected_terminal,
            "{}",
            test_case.description
        );
    }
}
