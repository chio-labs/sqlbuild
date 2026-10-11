use crate::assembly::analysis_session::main::model_reference_facts::model_reference_facts;
use crate::assembly::analysis_session::tests::test_types::ReferenceFactsTestCase;

#[test]
fn given_reference_rows_when_deriving_facts_then_python_lineage_map_and_required_names_match() {
    let test_cases = [
        ReferenceFactsTestCase {
            description: "a repeated name keeps its first position with the last resource type",
            rows: &[("ref", "orders"), ("seed", "codes"), ("source", "orders")],
            expected_lineage: &[("orders", "source", "orders"), ("codes", "seed", "codes")],
            expected_required: &["codes", "orders"],
        },
        ReferenceFactsTestCase {
            description: "table functions are renamed; UDFs and dbt refs are not lineage",
            rows: &[
                ("table_fn", "expand"),
                ("udf", "scale"),
                ("dbt_ref", "legacy"),
            ],
            expected_lineage: &[("__sqlbuild_table_function_expand", "table_fn", "expand")],
            expected_required: &["__sqlbuild_table_function_expand", "legacy"],
        },
    ];

    for test_case in test_cases {
        let rows: Vec<(String, String)> = test_case
            .rows
            .iter()
            .map(|(kind, name)| ((*kind).to_owned(), (*name).to_owned()))
            .collect();

        let facts = model_reference_facts(&rows);

        let lineage: Vec<(&str, &str, &str)> = facts
            .lineage_references
            .iter()
            .map(|(a, b, c)| (a.as_str(), b.as_str(), c.as_str()))
            .collect();
        assert_eq!(
            (
                lineage,
                facts
                    .required_names
                    .iter()
                    .map(String::as_str)
                    .collect::<Vec<_>>()
            ),
            (
                test_case.expected_lineage.to_vec(),
                test_case.expected_required.to_vec()
            ),
            "{}",
            test_case.description
        );
    }
}
