//! What a model analysis record answers without the host.

use sqlbuild_analysis::assembly::analysis_session::models::{LineageFacts, LineageRow};

use crate::models::AnalysisRecord;
use crate::types::ProjectHost;

impl<H: ProjectHost> AnalysisRecord<H> {
    /// The session's lineage rows, or `None` when the model kept no lineage.
    #[inline]
    pub fn lineage_rows(&self) -> Option<&[LineageRow]> {
        self.lineage.as_ref().map(|lineage| match lineage {
            LineageFacts::Native(rows) | LineageFacts::NativeFacts(rows) => rows.as_slice(),
        })
    }

    /// The number of upstream sources across the model's lineage rows, or `None` without lineage.
    pub fn lineage_edge_count(&self) -> Option<usize> {
        let rows: &[LineageRow] = self.lineage_rows()?;
        Some(rows.iter().map(|row| row.sources.len()).sum())
    }
}
