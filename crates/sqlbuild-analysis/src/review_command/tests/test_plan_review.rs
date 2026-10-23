use crate::review_command::main::parse_downstream_policy::parse_downstream_policy;
use crate::review_command::main::parse_review_schema_name::parse_review_schema_name;
use crate::review_command::main::plan_review::plan_review;
use crate::review_command::main::review_schema_name::review_schema_name;
use crate::review_command::models::{ChangedNode, DownstreamPolicy, ReviewPlan};
use crate::review_command::tests::helpers::{changed, token, waffle_shop};
use crate::review_command::tests::test_types::{
    PlanErrorTestCase, PlanTestCase, SchemaNameTestCase,
};

#[test]
fn given_changed_models_when_planning_then_validated_set_follows_policy_and_selection() {
    let test_cases = [
        PlanTestCase {
            description: "critical builds only the path to the critical model",
            changed: vec!["stg_orders"],
            policy: DownstreamPolicy::Critical,
            select: None,
            expected_validated: vec!["stg_orders", "order_totals", "daily_revenue"],
            expected_not_validated: vec![(
                "order_archive",
                "not on a path to a critical model (--downstream critical)",
            )],
        },
        PlanTestCase {
            description: "all builds every downstream node",
            changed: vec!["stg_orders"],
            policy: DownstreamPolicy::All,
            select: None,
            expected_validated: vec![
                "stg_orders",
                "order_archive",
                "order_totals",
                "daily_revenue",
            ],
            expected_not_validated: vec![],
        },
        PlanTestCase {
            description: "none builds only the changed model and lists its downstream",
            changed: vec!["stg_orders"],
            policy: DownstreamPolicy::None,
            select: None,
            expected_validated: vec!["stg_orders"],
            expected_not_validated: vec![
                (
                    "order_archive",
                    "downstream of a change (--downstream none)",
                ),
                ("order_totals", "downstream of a change (--downstream none)"),
                (
                    "daily_revenue",
                    "downstream of a change (--downstream none)",
                ),
            ],
        },
        PlanTestCase {
            description: "a changed critical model needs no downstream path",
            changed: vec!["daily_revenue"],
            policy: DownstreamPolicy::Critical,
            select: None,
            expected_validated: vec!["daily_revenue"],
            expected_not_validated: vec![],
        },
        PlanTestCase {
            description: "a change with no critical downstream builds only itself",
            changed: vec!["stg_customers"],
            policy: DownstreamPolicy::Critical,
            select: None,
            expected_validated: vec!["stg_customers"],
            expected_not_validated: vec![(
                "customer_lifetime",
                "not on a path to a critical model (--downstream critical)",
            )],
        },
        PlanTestCase {
            description: "select intersects with the planned scope",
            changed: vec!["stg_orders", "stg_customers"],
            policy: DownstreamPolicy::Critical,
            select: Some(vec![token("stg_orders", &["stg_orders"])]),
            expected_validated: vec!["stg_orders"],
            expected_not_validated: vec![
                ("stg_customers", "not selected (--select)"),
                (
                    "customer_lifetime",
                    "not on a path to a critical model (--downstream critical)",
                ),
                (
                    "order_archive",
                    "not on a path to a critical model (--downstream critical)",
                ),
                ("order_totals", "not selected (--select)"),
                ("daily_revenue", "not selected (--select)"),
            ],
        },
        PlanTestCase {
            description: "a graph selector keeps only its nodes inside the scope",
            changed: vec!["stg_orders"],
            policy: DownstreamPolicy::Critical,
            select: Some(vec![token(
                "stg_orders+",
                &[
                    "stg_orders",
                    "order_totals",
                    "daily_revenue",
                    "order_archive",
                ],
            )]),
            expected_validated: vec!["stg_orders", "order_totals", "daily_revenue"],
            expected_not_validated: vec![(
                "order_archive",
                "not on a path to a critical model (--downstream critical)",
            )],
        },
    ];
    for test_case in test_cases {
        let changed_nodes: Vec<ChangedNode> = test_case
            .changed
            .iter()
            .map(|name| changed(name, "model SQL changed"))
            .collect();

        let plan: ReviewPlan = plan_review(
            &waffle_shop(),
            &changed_nodes,
            test_case.policy,
            test_case.select.as_deref(),
        )
        .expect(test_case.description);

        assert_eq!(
            plan.validated, test_case.expected_validated,
            "{}",
            test_case.description
        );
        let not_validated: Vec<(&str, &str)> = plan
            .not_validated
            .iter()
            .map(|node| (node.name.as_str(), node.reason.as_str()))
            .collect();
        assert_eq!(
            not_validated, test_case.expected_not_validated,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_bad_selection_when_planning_then_fails_with_code() {
    let test_cases = [
        PlanErrorTestCase {
            description: "an unknown node",
            policy: DownstreamPolicy::Critical,
            select: vec![token("missing_model", &[])],
            expected_code: "C761",
            expected_fragment: "matches no model or seed",
        },
        PlanErrorTestCase {
            description: "an unchanged node",
            policy: DownstreamPolicy::Critical,
            select: vec![token("stg_customers", &["stg_customers"])],
            expected_code: "C762",
            expected_fragment: "did not change",
        },
        PlanErrorTestCase {
            description: "a downstream node outside the policy",
            policy: DownstreamPolicy::Critical,
            select: vec![token("order_archive", &["order_archive"])],
            expected_code: "C763",
            expected_fragment: "--downstream critical leaves out",
        },
        PlanErrorTestCase {
            description: "any downstream node under none",
            policy: DownstreamPolicy::None,
            select: vec![token("order_totals", &["order_totals"])],
            expected_code: "C763",
            expected_fragment: "--downstream none leaves out",
        },
    ];
    for test_case in test_cases {
        let error = plan_review(
            &waffle_shop(),
            &[changed("stg_orders", "model SQL changed")],
            test_case.policy,
            Some(&test_case.select),
        )
        .expect_err(test_case.description);

        assert_eq!(
            error.code, test_case.expected_code,
            "{}",
            test_case.description
        );
        assert!(
            error.message.contains(test_case.expected_fragment),
            "{}: {}",
            test_case.description,
            error.message
        );
    }
}

#[test]
fn given_policy_text_when_parsing_then_known_values_map() {
    assert_eq!(
        parse_downstream_policy("critical"),
        Some(DownstreamPolicy::Critical)
    );
    assert_eq!(parse_downstream_policy("all"), Some(DownstreamPolicy::All));
    assert_eq!(
        parse_downstream_policy("none"),
        Some(DownstreamPolicy::None)
    );
    assert_eq!(parse_downstream_policy("some"), None);
}

#[test]
fn given_schema_names_when_parsing_then_only_strict_names_parse() {
    let built: String =
        review_schema_name("REVIEW", "20261023T101500Z", "3F2A9C1D88", "a1b2c3d4e5f6");
    assert_eq!(built, "REVIEW_20261023T101500Z_3f2a9c1_a1b2c3");
    let test_cases = [
        SchemaNameTestCase {
            description: "a built name",
            name: "REVIEW_20261023T101500Z_3f2a9c1_a1b2c3",
            expected: Some((2026, 10, 23, 10, 15, 0)),
        },
        SchemaNameTestCase {
            description: "a folded name with an underscored prefix",
            name: "ci_review_20261023t101500z_3f2a9c1_a1b2c3",
            expected: Some((2026, 10, 23, 10, 15, 0)),
        },
        SchemaNameTestCase {
            description: "a short commit",
            name: "REVIEW_20261023T101500Z_3f2a_a1b2c3",
            expected: None,
        },
        SchemaNameTestCase {
            description: "an invalid month",
            name: "REVIEW_20261323T101500Z_3f2a9c1_a1b2c3",
            expected: None,
        },
        SchemaNameTestCase {
            description: "an ordinary schema",
            name: "analytics_prod",
            expected: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            parse_review_schema_name(test_case.name),
            test_case.expected,
            "{}",
            test_case.description
        );
    }
}
