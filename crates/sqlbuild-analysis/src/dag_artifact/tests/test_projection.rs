//! Orchestrator asset and check projections follow the integrations' artifact indexing.

use std::collections::BTreeSet;

use crate::dag_artifact::main::dag_asset_plans::dag_asset_plans;
use crate::dag_artifact::main::dag_asset_spec_kinds::dag_asset_spec_kinds;
use crate::dag_artifact::main::dag_check_plans::dag_check_plans;
use crate::dag_artifact::models::{
    AssetNodePlan, AssetProjectionPolicy, AssetSpecKindPolicy, CheckKindFilter, CheckPlan,
};
use crate::dag_artifact::tests::helpers::{asset_kinds, projection_graph};
use crate::dag_artifact::tests::test_types::{
    AssetPlansTestCase, CheckPlansTestCase, SpecKindsTestCase,
};

#[test]
fn given_artifact_graph_when_planning_assets_then_keeps_edge_order_and_last_duplicate() {
    let test_cases = [
        AssetPlansTestCase {
            description: "any known upstream node",
            upstream_asset_kinds_only: false,
            expected_plans: vec![(0, vec![]), (1, vec![2, 0]), (3, vec![2, 0])],
        },
        AssetPlansTestCase {
            description: "upstream asset nodes only",
            upstream_asset_kinds_only: true,
            expected_plans: vec![(0, vec![]), (1, vec![0]), (3, vec![0])],
        },
    ];
    for test_case in test_cases {
        let policy: AssetProjectionPolicy = AssetProjectionPolicy {
            asset_kinds: asset_kinds(),
            upstream_asset_kinds_only: test_case.upstream_asset_kinds_only,
        };
        let plans: Vec<(usize, Vec<usize>)> = dag_asset_plans(&projection_graph(), &policy)
            .into_iter()
            .map(|plan: AssetNodePlan| (plan.node, plan.upstream))
            .collect();
        assert_eq!(plans, test_case.expected_plans, "{}", test_case.description);
    }
}

#[test]
fn given_check_filter_when_planning_checks_then_marks_exposed_kinds() {
    let scenario: BTreeSet<String> = BTreeSet::from(["scenario".to_owned()]);
    let test_cases = [
        CheckPlansTestCase {
            description: "scenarios excluded",
            filter: CheckKindFilter {
                excluded: scenario.clone(),
                required: None,
            },
            expected_plans: vec![(0, false, vec![3]), (1, true, vec![0])],
        },
        CheckPlansTestCase {
            description: "scenarios only",
            filter: CheckKindFilter {
                excluded: BTreeSet::new(),
                required: Some(scenario.clone()),
            },
            expected_plans: vec![(0, true, vec![3]), (1, false, vec![0])],
        },
    ];
    for test_case in test_cases {
        let plans: Vec<(usize, bool, Vec<usize>)> =
            dag_check_plans(&projection_graph(), &test_case.filter)
                .into_iter()
                .map(|plan: CheckPlan| (plan.check, plan.included, plan.nodes))
                .collect();
        assert_eq!(plans, test_case.expected_plans, "{}", test_case.description);
    }
}

#[test]
fn given_asset_node_when_choosing_spec_kinds_then_reports_materialization_or_kind() {
    let test_cases = [
        SpecKindsTestCase {
            description: "view model",
            kind: "model",
            materialization_type: "view",
            expected_kinds: vec!["sqlbuild", "view"],
        },
        SpecKindsTestCase {
            description: "incremental model is a table",
            kind: "model",
            materialization_type: "incremental",
            expected_kinds: vec!["sqlbuild", "table"],
        },
        SpecKindsTestCase {
            description: "direct kind",
            kind: "seed",
            materialization_type: "table",
            expected_kinds: vec!["sqlbuild", "seed"],
        },
        SpecKindsTestCase {
            description: "other kind",
            kind: "check",
            materialization_type: "table",
            expected_kinds: vec!["sqlbuild"],
        },
    ];
    let policy: AssetSpecKindPolicy = AssetSpecKindPolicy {
        model_kind: "model".to_owned(),
        view_materialization: "view".to_owned(),
        direct_kinds: BTreeSet::from(["seed".to_owned()]),
    };
    for test_case in test_cases {
        assert_eq!(
            dag_asset_spec_kinds((test_case.kind, test_case.materialization_type), &policy),
            test_case.expected_kinds,
            "{}",
            test_case.description
        );
    }
}
