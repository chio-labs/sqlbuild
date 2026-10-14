use std::collections::HashMap;

use crate::planner_fixtures::main::propagate_types::propagate_types;
use crate::planner_fixtures::models::FixtureTypeState;
use crate::planner_fixtures::tests::{helpers::type_model, test_types::PropagationTestCase};

#[test]
fn given_upstream_types_when_propagating_then_only_agreed_known_types_are_used() {
    let test_cases = [
        PropagationTestCase {
            description: "matching known types",
            upstream_type: Some("INTEGER"),
            expected_type: Some("INTEGER"),
        },
        PropagationTestCase {
            description: "conflicting known types",
            upstream_type: Some("VARCHAR"),
            expected_type: None,
        },
        PropagationTestCase {
            description: "unknown type ignored",
            upstream_type: None,
            expected_type: Some("INTEGER"),
        },
    ];
    for test_case in test_cases {
        let mut state = FixtureTypeState::default();
        state.known.insert(
            ("source".into(), "orders".into()),
            HashMap::from([("order_id".into(), "INTEGER".into())]),
        );
        state.known.insert(
            ("source".into(), "customers".into()),
            test_case
                .upstream_type
                .into_iter()
                .map(|sql_type| ("customer_id".into(), sql_type.into()))
                .collect(),
        );
        let state = propagate_types(state, &[type_model()]);
        assert_eq!(
            state
                .additions
                .first()
                .map(|(_, sql_type)| sql_type.as_str()),
            test_case.expected_type,
            "{}",
            test_case.description
        );
    }
}
