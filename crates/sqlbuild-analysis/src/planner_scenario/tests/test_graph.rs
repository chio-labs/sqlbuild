//! Validate fixture cuts, shared dependencies, and diagnostic ordering.

use crate::planner_scenario::main::graph::graph;
use crate::planner_scenario::models::ScenarioGraphInput;
use crate::planner_scenario::tests::test_types::GraphTestCase;

#[test]
fn given_scenario_dependencies_when_planning_then_preserves_closure_and_warning_order() {
    let test_cases = [
        GraphTestCase {
            description: "fixture cut and shared function dependency",
            input: ScenarioGraphInput {
                name: "orders".into(),
                targets: vec!["summary".into()],
                refs: vec!["staging".into()],
                models: [
                    (
                        "summary".into(),
                        vec![
                            ("model".into(), "staging".into()),
                            ("udf".into(), "total".into()),
                            ("model".into(), "details".into()),
                        ],
                    ),
                    ("staging".into(), vec![("source".into(), "hidden".into())]),
                    (
                        "details".into(),
                        vec![
                            ("udf".into(), "total".into()),
                            ("table_fn".into(), "items".into()),
                            ("model".into(), "summary".into()),
                        ],
                    ),
                ]
                .into(),
                ..ScenarioGraphInput::default()
            },
            expected_models: vec!["details", "summary"],
            expected_refs: vec!["staging"],
            expected_functions: vec![("udf", "total"), ("table_fn", "items")],
            expected_warnings: vec![],
        },
        GraphTestCase {
            description: "declared and upstream diagnostic ordering",
            input: ScenarioGraphInput {
                name: "orders".into(),
                targets: vec!["summary".into()],
                expected: vec!["unknown".into()],
                models: [(
                    "summary".into(),
                    vec![
                        ("source".into(), "raw.orders".into()),
                        ("model".into(), "missing".into()),
                        ("dbt_ref".into(), "catalog.items".into()),
                    ],
                )]
                .into(),
                ..ScenarioGraphInput::default()
            },
            expected_models: vec!["summary"],
            expected_refs: vec![],
            expected_functions: vec![],
            expected_warnings: vec![
                ("Scenario 'orders' expects unknown model 'unknown'.", true),
                (
                    "Scenario 'orders' requires model 'missing', but it does not exist and no __ref__ fixture was provided.",
                    true,
                ),
                (
                    "Scenario 'orders' requires source 'raw.orders', but no fixture was provided. Add a CTE named __source__raw__orders AS (...).",
                    false,
                ),
                (
                    "Scenario 'orders' requires dbt ref 'catalog__items', but no fixture was provided. Add a CTE named __dbt_ref__catalog__items AS (...).",
                    false,
                ),
            ],
        },
    ];
    for test_case in test_cases {
        let result = graph(&test_case.input);
        assert_eq!(
            result.models.iter().map(String::as_str).collect::<Vec<_>>(),
            test_case.expected_models,
            "{}",
            test_case.description
        );
        assert_eq!(
            result.refs.iter().map(String::as_str).collect::<Vec<_>>(),
            test_case.expected_refs,
            "{}",
            test_case.description
        );
        assert_eq!(
            result
                .functions
                .iter()
                .map(|(kind, name)| (kind.as_str(), name.as_str()))
                .collect::<Vec<_>>(),
            test_case.expected_functions,
            "{}",
            test_case.description
        );
        assert_eq!(
            result
                .warnings
                .iter()
                .map(|(message, code)| (message.as_str(), *code))
                .collect::<Vec<_>>(),
            test_case.expected_warnings,
            "{}",
            test_case.description
        );
    }
}
