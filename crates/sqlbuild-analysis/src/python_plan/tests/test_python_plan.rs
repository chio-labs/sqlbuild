use crate::python_plan::main::ordered_python_names::ordered_python_names;
use crate::python_plan::main::upstream_closure::upstream_closure;
use crate::python_plan::tests::helpers::edges;
use crate::python_plan::tests::test_types::{ClosureTestCase, OrderTestCase};

#[test]
fn given_selected_nodes_when_ordering_then_matches_python_ready_queue() {
    let test_cases = [
        OrderTestCase {
            description: "ready nodes go by name, dependents after their upstreams",
            selected: &["load_orders", "clean_orders", "audit_orders", "fetch_rates"],
            upstream: &[
                ("clean_orders", &["load_orders", "fetch_rates"]),
                ("audit_orders", &["clean_orders", "unselected"]),
            ],
            expected_order: &["fetch_rates", "load_orders", "clean_orders", "audit_orders"],
        },
        OrderTestCase {
            description: "nodes on a cycle are left out",
            selected: &["a", "b", "c"],
            upstream: &[("a", &["b"]), ("b", &["a"])],
            expected_order: &["c"],
        },
    ];

    for test_case in test_cases {
        let selected: Vec<String> = test_case
            .selected
            .iter()
            .map(|name| (*name).to_owned())
            .collect();

        let order = ordered_python_names(&selected, &edges(test_case.upstream));

        assert_eq!(order, test_case.expected_order, "{}", test_case.description);
    }
}

#[test]
fn given_start_when_closing_upstream_then_matches_python_transitive_closure() {
    let test_cases = [
        ClosureTestCase {
            description: "every upstream, sorted, without the start",
            start: "load",
            upstream: &[("load", &["fetch", "auth"]), ("fetch", &["auth"])],
            expected_closure: &["auth", "fetch"],
        },
        ClosureTestCase {
            description: "the start is included when it is on a cycle",
            start: "a",
            upstream: &[("a", &["b"]), ("b", &["a"])],
            expected_closure: &["a", "b"],
        },
    ];

    for test_case in test_cases {
        let closure = upstream_closure(test_case.start, &edges(test_case.upstream));

        assert_eq!(
            closure, test_case.expected_closure,
            "{}",
            test_case.description
        );
    }
}
