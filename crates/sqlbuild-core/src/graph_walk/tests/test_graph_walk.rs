use std::cmp::Reverse;
use std::collections::{BTreeSet, BinaryHeap, VecDeque};

use crate::graph_walk::main::breadth_first_path::breadth_first_path;
use crate::graph_walk::main::breadth_first_reach::breadth_first_reach;
use crate::graph_walk::main::depth_first_postorder::depth_first_postorder;
use crate::graph_walk::main::directed_path_nodes::directed_path_nodes;
use crate::graph_walk::main::find_cycle::find_cycle;
use crate::graph_walk::models::VisitOrder;
use crate::graph_walk::tests::helpers::{
    adjacency, inverted, kahn_case_order, neighbours, recorded_starts,
};
use crate::graph_walk::tests::test_types::{
    CycleTestCase, GoalPathTestCase, KahnTestCase, OrderTestCase, PathTestCase, ReachTestCase,
};

#[test]
fn given_starts_when_reaching_breadth_first_then_records_nodes_in_first_visit_order() {
    let test_cases = [
        ReachTestCase {
            description: "starts are left out unless reached again",
            edges: &[("a", &["b", "c"]), ("b", &["d", "a"]), ("c", &["d"])],
            starts: &["a"],
            include_starts: false,
            max_depth: None,
            expected_order: vec!["b", "c", "d", "a"],
        },
        ReachTestCase {
            description: "recorded starts lead and are not expanded twice",
            edges: &[("a", &["c"]), ("b", &["a", "d"]), ("c", &["b"])],
            starts: &["b", "a", "b"],
            include_starts: true,
            max_depth: None,
            expected_order: vec!["b", "a", "d", "c"],
        },
        ReachTestCase {
            description: "a depth limit stops expansion at that distance",
            edges: &[("a", &["b"]), ("b", &["c"]), ("c", &["d"])],
            starts: &["a"],
            include_starts: false,
            max_depth: Some(2),
            expected_order: vec!["b", "c"],
        },
        ReachTestCase {
            description: "a zero depth limit reaches nothing",
            edges: &[("a", &["b"])],
            starts: &["a"],
            include_starts: false,
            max_depth: Some(0),
            expected_order: vec![],
        },
    ];
    for test_case in test_cases {
        let edges = adjacency(test_case.edges);
        let mut visited: VisitOrder<&str> =
            recorded_starts(test_case.starts, test_case.include_starts);
        let Ok(()) = breadth_first_reach(
            test_case.starts.iter().copied(),
            test_case.max_depth,
            &mut visited,
            |node| Ok(neighbours(&edges, node)),
        );
        assert_eq!(
            visited.order, test_case.expected_order,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_endpoints_when_collecting_path_nodes_then_keeps_nodes_between_them() {
    let test_cases = [
        PathTestCase {
            description: "branches off the paths are left out",
            edges: &[("a", &["b", "x"]), ("b", &["c"]), ("x", &["y"]), ("c", &[])],
            endpoints: ("a", "c"),
            expected_nodes: Some(vec!["a", "b", "c"]),
        },
        PathTestCase {
            description: "parallel paths are all kept",
            edges: &[
                ("a", &["b", "c"]),
                ("b", &["d"]),
                ("c", &["d"]),
                ("z", &["d"]),
            ],
            endpoints: ("a", "d"),
            expected_nodes: Some(vec!["a", "b", "c", "d"]),
        },
        PathTestCase {
            description: "an end not downstream of the start has no path",
            edges: &[("a", &["b"]), ("c", &["a"])],
            endpoints: ("a", "c"),
            expected_nodes: None,
        },
    ];
    for test_case in test_cases {
        let downstream = adjacency(test_case.edges);
        let upstream = inverted(test_case.edges);
        let mut reachable: BTreeSet<&str> = BTreeSet::new();
        let mut path: BTreeSet<&str> = BTreeSet::new();
        let Ok(found) = directed_path_nodes(
            test_case.endpoints,
            (
                |node: &&'static str| Ok(neighbours(&downstream, node)),
                |node: &&'static str| Ok(neighbours(&upstream, node)),
            ),
            (&mut reachable, &mut path),
        );
        let nodes: Option<Vec<&str>> = found.then(|| path.into_iter().collect());
        assert_eq!(nodes, test_case.expected_nodes, "{}", test_case.description);
    }
}

#[test]
fn given_goals_when_searching_breadth_first_then_returns_the_shortest_path() {
    let test_cases = [
        GoalPathTestCase {
            description: "the first goal met on the shortest path ends the search",
            edges: &[("a", &["b", "c"]), ("b", &["g"]), ("c", &["h"])],
            origin: "a",
            goals: &["g", "h"],
            blocked: &[],
            expected_path: Some(vec!["a", "b", "g"]),
        },
        GoalPathTestCase {
            description: "the origin can be the goal that closes a cycle",
            edges: &[("a", &["b"]), ("b", &["a"])],
            origin: "a",
            goals: &["a"],
            blocked: &[],
            expected_path: Some(vec!["a", "b", "a"]),
        },
        GoalPathTestCase {
            description: "blocked nodes are not entered",
            edges: &[("a", &["b"]), ("b", &["g"])],
            origin: "a",
            goals: &["g"],
            blocked: &["b"],
            expected_path: None,
        },
    ];
    for test_case in test_cases {
        let edges = adjacency(test_case.edges);
        let path: Option<Vec<&str>> = breadth_first_path(
            test_case.origin,
            (
                |node: &&'static str| neighbours(&edges, node),
                |node: &&'static str| test_case.goals.contains(node),
                |node: &&'static str| !test_case.blocked.contains(node),
            ),
        );
        assert_eq!(path, test_case.expected_path, "{}", test_case.description);
    }
}

#[test]
fn given_counts_when_ordering_first_in_first_out_then_keeps_node_order_among_ready_nodes() {
    let test_cases = [
        KahnTestCase {
            description: "ready nodes leave in node order",
            edges: &[("c", &["a"]), ("b", &["a"]), ("a", &[])],
            nodes: &["c", "b", "a"],
            expected_order: vec!["c", "b", "a"],
        },
        KahnTestCase {
            description: "repeated edges lower the count once each",
            edges: &[("a", &["b", "b"]), ("b", &[])],
            nodes: &["a", "b"],
            expected_order: vec!["a", "b"],
        },
        KahnTestCase {
            description: "nodes on a cycle are left out",
            edges: &[("a", &["b"]), ("b", &["c"]), ("c", &["b"])],
            nodes: &["a", "b", "c"],
            expected_order: vec!["a"],
        },
    ];
    for test_case in test_cases {
        let order: Vec<&str> = kahn_case_order(&test_case, VecDeque::new());
        assert_eq!(order, test_case.expected_order, "{}", test_case.description);
    }
}

#[test]
fn given_counts_when_ordering_smallest_first_then_takes_the_smallest_ready_node() {
    let test_cases = [KahnTestCase {
        description: "the smallest ready node leaves first",
        edges: &[("c", &["a"]), ("b", &["a"]), ("a", &[])],
        nodes: &["c", "b", "a"],
        expected_order: vec!["b", "c", "a"],
    }];
    for test_case in test_cases {
        let order: Vec<&str> =
            kahn_case_order(&test_case, BinaryHeap::<Reverse<&'static str>>::new());
        assert_eq!(order, test_case.expected_order, "{}", test_case.description);
    }
}

#[test]
fn given_roots_when_ordering_depth_first_then_places_nodes_after_their_neighbours() {
    let test_cases = [
        OrderTestCase {
            description: "neighbours come first in their given order",
            edges: &[("a", &["c", "b"]), ("b", &["d"]), ("c", &["d"])],
            roots: &["a"],
            expected_order: vec!["d", "c", "b", "a"],
        },
        OrderTestCase {
            description: "later roots skip nodes already placed",
            edges: &[("b", &["c"]), ("a", &["c"])],
            roots: &["b", "a"],
            expected_order: vec!["c", "b", "a"],
        },
        OrderTestCase {
            description: "a cycle back to an entered node is not followed",
            edges: &[("a", &["b"]), ("b", &["a"])],
            roots: &["a"],
            expected_order: vec!["b", "a"],
        },
    ];
    for test_case in test_cases {
        let edges = adjacency(test_case.edges);
        let order: Vec<&str> = depth_first_postorder(test_case.roots.iter().copied(), |node| {
            neighbours(&edges, node)
        });
        assert_eq!(order, test_case.expected_order, "{}", test_case.description);
    }
}

#[test]
fn given_roots_when_searching_for_cycles_then_returns_the_path_to_the_repeat() {
    let test_cases = [
        CycleTestCase {
            description: "the path runs from the root to the repeated node",
            edges: &[("a", &["b"]), ("b", &["c"]), ("c", &["b"])],
            roots: &["a"],
            expected_cycle: Some(vec!["a", "b", "c", "b"]),
        },
        CycleTestCase {
            description: "shared finished nodes are not a cycle",
            edges: &[("a", &["c"]), ("b", &["c"]), ("c", &[])],
            roots: &["a", "b"],
            expected_cycle: None,
        },
        CycleTestCase {
            description: "a self edge is a cycle",
            edges: &[("a", &["a"])],
            roots: &["a"],
            expected_cycle: Some(vec!["a", "a"]),
        },
        CycleTestCase {
            description: "a later root finds a cycle the earlier roots missed",
            edges: &[("a", &[]), ("b", &["c"]), ("c", &["b"])],
            roots: &["a", "b"],
            expected_cycle: Some(vec!["b", "c", "b"]),
        },
    ];
    for test_case in test_cases {
        let edges = adjacency(test_case.edges);
        let cycle: Option<Vec<&str>> = find_cycle(test_case.roots.iter().copied(), |node| {
            neighbours(&edges, node)
        });
        assert_eq!(cycle, test_case.expected_cycle, "{}", test_case.description);
    }
}
