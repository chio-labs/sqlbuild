use sqlbuild_analysis::assembly::analysis_session::models::{LineageFacts, LineageRow};

use crate::models::AnalysisRecord;
use crate::tests::test_types::TestHost;

pub(super) fn lineage_row(output: &str, sources: &[&str]) -> LineageRow {
    LineageRow {
        output_column: output.to_owned(),
        transform_code: 0,
        confidence_code: 0,
        sources: sources
            .iter()
            .map(|source| {
                (
                    "orders".to_owned(),
                    (*source).to_owned(),
                    "model".to_owned(),
                )
            })
            .collect(),
    }
}

pub(super) fn analysis(lineage: Option<LineageFacts>) -> AnalysisRecord<TestHost> {
    AnalysisRecord {
        inferred: None,
        lineage,
        has_star: false,
        star_resolved: false,
        binding: Vec::new(),
        binding_validated: false,
        proof: None,
        host: (),
    }
}
