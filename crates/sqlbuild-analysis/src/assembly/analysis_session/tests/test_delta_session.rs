use crate::assembly::analysis_session::models::{ModelRequest, RelationTables, SessionRequest};
use crate::assembly::analysis_session::tests::helpers::{
    completed, model_requests, orders_request, started,
};
use crate::assembly::analysis_session::tests::test_types::ModelSpec;

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

/// `request` with `relations`' facts added for every relation it does not analyse.
fn injected(mut request: SessionRequest, relations: &RelationTables) -> SessionRequest {
    let analysed: Vec<String> = request
        .models
        .iter()
        .map(|model| model.name.clone())
        .collect();
    for (table, facts) in [
        (&mut request.column_types, &relations.types),
        (&mut request.column_nullability, &relations.nullability),
        (&mut request.complete_schemas, &relations.complete),
    ] {
        let present: Vec<String> = table.iter().map(|(name, _)| name.clone()).collect();
        table.extend(
            facts
                .iter()
                .filter(|(name, _)| !analysed.contains(name) && !present.contains(name))
                .cloned(),
        );
    }
    request.forced_order = Some((relations.dependency_ordered, relations.cyclic));
    request
}

#[test]
fn given_whole_project_relations_when_analysing_one_model_then_it_matches_the_whole_session() {
    let mut whole: SessionRequest = orders_request(model_requests(&ORDER_MODELS));
    whole.retain_relations = true;
    let (_, whole_outcomes, finished) = completed(started(whole));
    let relations: RelationTables = finished.relation_tables().cloned().expect("relations kept");
    assert!(relations.types.iter().any(|(name, _)| name == "stg_orders"));

    for (index, spec) in ORDER_MODELS.iter().enumerate().skip(1) {
        let one: Vec<ModelRequest> = model_requests(std::slice::from_ref(spec));
        let request: SessionRequest = injected(orders_request(one), &relations);
        let (_, outcomes, _) = completed(started(request));

        assert_eq!(outcomes, vec![whole_outcomes[index].clone()], "{}", spec.0);
    }
}
