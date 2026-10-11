use crate::audits::main::singular_audit_resources::singular_audit_resources;
use crate::audits::tests::test_types::SingularResourcesTestCase;

#[test]
fn given_singular_audit_references_when_collecting_resources_then_cross_resource_rule_applies() {
    let test_cases = [
        SingularResourcesTestCase {
            description: "two models are cross-resource",
            references: vec![("ref", "orders"), ("ref", "customers"), ("ref", "orders")],
            expected_resources: vec![("model", "customers"), ("model", "orders")],
            expected_problem: None,
        },
        SingularResourcesTestCase {
            description: "a model and a source are cross-resource",
            references: vec![("source", "raw_orders"), ("ref", "orders")],
            expected_resources: vec![("model", "orders"), ("source", "raw_orders")],
            expected_problem: None,
        },
        SingularResourcesTestCase {
            description: "one model alone names the model",
            references: vec![("ref", "orders")],
            expected_resources: vec![("model", "orders")],
            expected_problem: Some(
                "checks only model 'orders'; singular audits must be cross-resource",
            ),
        },
        SingularResourcesTestCase {
            description: "sources and seeds alone need a model",
            references: vec![("source", "raw_orders"), ("seed", "regions")],
            expected_resources: vec![("seed", "regions"), ("source", "raw_orders")],
            expected_problem: Some(
                "checks only sources or seeds; singular audits must reference at least one model",
            ),
        },
    ];

    for test_case in test_cases {
        let resources = singular_audit_resources(&test_case.references);
        assert_eq!(
            resources
                .resources
                .iter()
                .map(|(kind, name)| (kind.as_str(), name.as_str()))
                .collect::<Vec<_>>(),
            test_case.expected_resources,
            "{}",
            test_case.description
        );
        assert_eq!(
            resources.problem.as_ref().map(|problem| problem.0.as_str()),
            test_case.expected_problem,
            "{}",
            test_case.description
        );
    }
}
