use std::collections::BTreeSet;

use crate::python_plan::main::run_lifecycle::run_lifecycle;
use crate::python_plan::tests::helpers::{edges, lifecycle_nodes};
use crate::python_plan::tests::test_types::LifecycleTestCase;

#[test]
fn given_selection_when_classifying_lifecycle_then_matches_python_regions() {
    let test_cases = [
        LifecycleTestCase {
            description: "a warehouse loader pulls its selected upstream tasks into ingress",
            selected: &["fetch_rates", "load_orders", "report", "check_orders"],
            nodes: &[
                ("fetch_rates", "task", false),
                ("load_orders", "loader", false),
                ("report", "asset", false),
                ("check_orders", "check", false),
            ],
            upstream: &[("load_orders", &["fetch_rates", "unselected"])],
            expected_ingress: &["fetch_rates", "load_orders"],
            expected_loaders: &["load_orders"],
            expected_read_side: &["report"],
        },
        LifecycleTestCase {
            description: "external loaders are neither ingress loaders nor read-side nodes",
            selected: &["sync_orders", "export"],
            nodes: &[("sync_orders", "loader", true), ("export", "task", false)],
            upstream: &[("export", &["sync_orders"])],
            expected_ingress: &[],
            expected_loaders: &[],
            expected_read_side: &["export"],
        },
        LifecycleTestCase {
            description: "a selected external loader upstream of a warehouse loader is ingress",
            selected: &["sync_orders", "load_orders"],
            nodes: &[
                ("sync_orders", "loader", true),
                ("load_orders", "loader", false),
            ],
            upstream: &[("load_orders", &["sync_orders"])],
            expected_ingress: &["load_orders", "sync_orders"],
            expected_loaders: &["load_orders"],
            expected_read_side: &[],
        },
    ];

    for test_case in test_cases {
        let selected: BTreeSet<String> = test_case
            .selected
            .iter()
            .map(|name| (*name).to_owned())
            .collect();

        let lifecycle = run_lifecycle(
            &selected,
            &lifecycle_nodes(test_case.nodes),
            &edges(test_case.upstream),
        );

        assert_eq!(
            (
                lifecycle.ingress_names,
                lifecycle.ingress_loader_names,
                lifecycle.read_side_names,
            ),
            (
                test_case
                    .expected_ingress
                    .iter()
                    .map(|name| (*name).to_owned())
                    .collect::<Vec<String>>(),
                test_case
                    .expected_loaders
                    .iter()
                    .map(|name| (*name).to_owned())
                    .collect::<Vec<String>>(),
                test_case
                    .expected_read_side
                    .iter()
                    .map(|name| (*name).to_owned())
                    .collect::<Vec<String>>(),
            ),
            "{}",
            test_case.description
        );
    }
}
