//! Invocation arguments and DAG order follow the CLI contract.

use crate::dagster_invocation::main::caller_json_output_path::caller_json_output_path;
use crate::dagster_invocation::main::has_explicit_scenario_selector::has_explicit_scenario_selector;
use crate::dagster_invocation::main::json_output_requested::json_output_requested;
use crate::dagster_invocation::main::topological_order::topological_order;
use crate::dagster_invocation::tests::helpers::owned;
use crate::dagster_invocation::tests::test_types::{ArgumentsTestCase, OrderTestCase};

#[test]
fn given_cli_arguments_when_reading_flags_then_reports_selectors_and_json_output() {
    let test_cases = [
        ArgumentsTestCase {
            description: "flag values are not selectors",
            args: vec!["scenario", "test", "--max-snapshot-rows", "10", "--json"],
            expected_explicit_scenario: false,
            expected_json_requested: true,
            expected_json_path: None,
        },
        ArgumentsTestCase {
            description: "a bare argument is a selector",
            args: vec![
                "scenario",
                "test",
                "orders_scenario",
                "--json-output",
                "out.json",
            ],
            expected_explicit_scenario: true,
            expected_json_requested: true,
            expected_json_path: Some("out.json"),
        },
        ArgumentsTestCase {
            description: "equals form with an empty path is not a path",
            args: vec!["build", "--json-output=", "--json-output=run.json"],
            expected_explicit_scenario: false,
            expected_json_requested: true,
            expected_json_path: Some("run.json"),
        },
        ArgumentsTestCase {
            description: "no JSON flags",
            args: vec!["build", "--select", "orders"],
            expected_explicit_scenario: true,
            expected_json_requested: false,
            expected_json_path: None,
        },
    ];
    for test_case in test_cases {
        let args: Vec<String> = owned(&test_case.args);
        assert_eq!(
            (
                has_explicit_scenario_selector(&args),
                json_output_requested(&args),
                caller_json_output_path(&args),
            ),
            (
                test_case.expected_explicit_scenario,
                test_case.expected_json_requested,
                test_case.expected_json_path.map(str::to_owned),
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_dag_edges_when_ordering_then_returns_kahn_order_or_none_on_cycles() {
    let test_cases = [
        OrderTestCase {
            description: "upstream before downstream, ties in node order",
            ids: vec!["orders", "customers", "raw"],
            edges: vec![("raw", "orders"), ("raw", "customers"), ("raw", "missing")],
            expected_order: Some(vec![2, 0, 1]),
        },
        OrderTestCase {
            description: "cycle keeps original order",
            ids: vec!["a", "b"],
            edges: vec![("a", "b"), ("b", "a")],
            expected_order: None,
        },
    ];
    for test_case in test_cases {
        let edges: Vec<(String, String)> = test_case
            .edges
            .iter()
            .map(|(from, to)| ((*from).to_owned(), (*to).to_owned()))
            .collect();
        assert_eq!(
            topological_order(&owned(&test_case.ids), &edges),
            test_case.expected_order,
            "{}",
            test_case.description
        );
    }
}
