use sqlbuild_analysis::assembly::analysis_session::models::{LineageFacts, LineageRow};

use crate::models::AnalysisRecord;
use crate::tests::helpers::{analysis, lineage_row};
use crate::tests::test_types::{LineageTestCase, TestHost};

#[test]
fn given_analysis_lineage_when_reading_then_rows_and_edges_follow_the_kept_facts() {
    let test_cases = [
        LineageTestCase {
            description: "a model without lineage has no rows or edges",
            lineage: None,
            expected_outputs: None,
            expected_edge_count: None,
        },
        LineageTestCase {
            description: "native rows count every upstream source",
            lineage: Some(LineageFacts::Native(vec![
                lineage_row("order_id", &["order_id"]),
                lineage_row("total", &["amount", "tax"]),
            ])),
            expected_outputs: Some(vec!["order_id", "total"]),
            expected_edge_count: Some(3),
        },
        LineageTestCase {
            description: "plain facts read the same as native rows",
            lineage: Some(LineageFacts::NativeFacts(vec![lineage_row("status", &[])])),
            expected_outputs: Some(vec!["status"]),
            expected_edge_count: Some(0),
        },
    ];

    for test_case in test_cases {
        let record: AnalysisRecord<TestHost> = analysis(test_case.lineage);
        let outputs: Option<Vec<&str>> = record
            .lineage_rows()
            .map(|rows: &[LineageRow]| rows.iter().map(|row| row.output_column.as_str()).collect());

        assert_eq!(
            outputs, test_case.expected_outputs,
            "{}",
            test_case.description
        );
        assert_eq!(
            record.lineage_edge_count(),
            test_case.expected_edge_count,
            "{}",
            test_case.description
        );
    }
}
