use sqlbuild_analysis::compiled_project::models::ModelSchemaFact;

use crate::models::{CompiledProject, ModelInputRecord};
use crate::tests::helpers::{model_input, schema_facts};
use crate::tests::test_types::{ProjectInputTestCase, TestHost};

#[test]
fn given_retained_inputs_when_reading_then_indexes_and_schema_facts_follow_loop_order() {
    let test_cases = [
        ProjectInputTestCase {
            description: "inputs keep loop order and their recorded schema",
            retained: &["orders", "customers"],
            recorded_schemas: &["customers"],
            read_index: 1,
            expected_indexes: vec![0, 1],
            expected_name: Some("customers"),
            expected_schema_column: Some("customer_id"),
        },
        ProjectInputTestCase {
            description: "an input without recorded facts has no schema",
            retained: &["orders"],
            recorded_schemas: &[],
            read_index: 0,
            expected_indexes: vec![0],
            expected_name: Some("orders"),
            expected_schema_column: None,
        },
        ProjectInputTestCase {
            description: "an index past the last input reads nothing",
            retained: &["orders"],
            recorded_schemas: &["orders"],
            read_index: 1,
            expected_indexes: vec![0],
            expected_name: None,
            expected_schema_column: None,
        },
    ];

    for test_case in test_cases {
        let mut project: CompiledProject<TestHost> = CompiledProject::default();
        for name in test_case.recorded_schemas {
            project.retain(schema_facts(
                name,
                &format!("{}_id", name.trim_end_matches('s')),
            ));
        }
        let indexes: Vec<usize> = test_case
            .retained
            .iter()
            .map(|name| project.retain_input(model_input(name)))
            .collect();
        let input: Option<&ModelInputRecord<TestHost>> = project.input(test_case.read_index);
        let schema: Option<&ModelSchemaFact> =
            input.and_then(|record| project.input_schema_fact(record));

        assert_eq!(
            indexes, test_case.expected_indexes,
            "{}",
            test_case.description
        );
        assert_eq!(
            input.map(|record| record.name.as_str()),
            test_case.expected_name,
            "{}",
            test_case.description
        );
        assert_eq!(
            schema
                .and_then(|schema| schema.columns.first())
                .map(|column| column.name.as_str()),
            test_case.expected_schema_column,
            "{}",
            test_case.description
        );
    }
}
