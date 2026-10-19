use crate::assembly::analysis_session::models::{ModelRequest, RelationTables, SessionRequest};
use crate::assembly::analysis_session::tests::helpers::{
    completed, injected_relations, model_requests, orders_request, started,
};
use crate::assembly::analysis_session::tests::test_types::{DeltaSessionTestCase, ModelSpec};

const ORDER_MODELS: [ModelSpec; 3] = [
    (
        "stg_orders",
        "SELECT order_id, amount * 2 AS doubled FROM __source(\"raw_orders\")",
        &["raw_orders"],
        &[],
    ),
    (
        "orders_mart",
        "SELECT doubled, order_id + 1 AS next_id FROM __ref(\"stg_orders\")",
        &[],
        &["stg_orders"],
    ),
    (
        "orders_star",
        "SELECT * FROM __ref(\"stg_orders\")",
        &[],
        &["stg_orders"],
    ),
];

#[test]
fn given_whole_project_relations_when_analysing_one_model_then_it_matches_the_whole_session() {
    let test_cases = [
        DeltaSessionTestCase {
            description: "a model reading another model's columns",
            model_index: 1,
            expected_whole_session_outcome: true,
        },
        DeltaSessionTestCase {
            description: "a model selecting every column of another model",
            model_index: 2,
            expected_whole_session_outcome: true,
        },
    ];
    let mut whole: SessionRequest = orders_request(model_requests(&ORDER_MODELS));
    whole.retain_relations = true;
    let (_, whole_outcomes, finished) = completed(started(whole));
    let relations: RelationTables = finished.relation_tables().cloned().expect("relations kept");
    for test_case in test_cases {
        let spec: &ModelSpec = &ORDER_MODELS[test_case.model_index];
        let one: Vec<ModelRequest> = model_requests(std::slice::from_ref(spec));
        let request: SessionRequest = injected_relations(orders_request(one), &relations);

        let (_, outcomes, _) = completed(started(request));

        assert_eq!(
            outcomes == vec![whole_outcomes[test_case.model_index].clone()],
            test_case.expected_whole_session_outcome,
            "{}",
            test_case.description
        );
    }
}
