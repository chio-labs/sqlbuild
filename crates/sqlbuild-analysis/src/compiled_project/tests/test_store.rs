use crate::compiled_project::main::model_facts::model_facts;
use crate::compiled_project::main::record_model::record_model;
use crate::compiled_project::main::record_model_analysis::record_model_analysis;
use crate::compiled_project::models::CompiledProjectFacts;
use crate::compiled_project::tests::helpers::{analysis, model};
use crate::compiled_project::tests::test_types::RecordTestCase;

#[test]
fn given_recorded_models_when_reading_then_order_and_latest_facts_are_kept() {
    let test_cases = [
        RecordTestCase {
            description: "production order is kept",
            recorded: vec![model("orders", "SELECT 1"), model("customers", "SELECT 2")],
            analysed: "orders",
            expected_order: &["orders", "customers"],
            expected_query_sql: "SELECT 1",
            expected_analysis_recorded: true,
        },
        RecordTestCase {
            description: "recording a model again replaces it in place",
            recorded: vec![
                model("orders", "SELECT 1"),
                model("customers", "SELECT 2"),
                model("orders", "SELECT 3"),
            ],
            analysed: "orders",
            expected_order: &["orders", "customers"],
            expected_query_sql: "SELECT 3",
            expected_analysis_recorded: true,
        },
        RecordTestCase {
            description: "analysis for an unrecorded model is refused",
            recorded: vec![model("orders", "SELECT 1")],
            analysed: "payments",
            expected_order: &["orders"],
            expected_query_sql: "SELECT 1",
            expected_analysis_recorded: false,
        },
    ];

    for test_case in test_cases {
        let mut project: CompiledProjectFacts = CompiledProjectFacts::default();
        for recorded in test_case.recorded {
            record_model(&mut project, recorded);
        }
        let recorded_analysis: bool =
            record_model_analysis(&mut project, test_case.analysed, analysis("order_id"));
        let order: Vec<&str> = project
            .models
            .iter()
            .map(|facts| facts.name.as_str())
            .collect();
        let query_sql: Option<&str> =
            model_facts(&project, "orders").map(|facts| facts.query_sql.as_str());

        assert_eq!(order, test_case.expected_order, "{}", test_case.description);
        assert_eq!(
            query_sql,
            Some(test_case.expected_query_sql),
            "{}",
            test_case.description
        );
        assert_eq!(
            recorded_analysis, test_case.expected_analysis_recorded,
            "{}",
            test_case.description
        );
    }
}
