//! The Polyglot analysis dialect for a stripped, lowercased adapter dialect name.

use crate::lineage_graph::constants::ANALYSIS_DIALECT_ALIASES;
use crate::lineage_graph::models::AnalysisDialect;

/// The aliased dialect value, or the name to look up as a dialect value.
pub fn analysis_dialect(normalized: &str) -> AnalysisDialect<'_> {
    ANALYSIS_DIALECT_ALIASES
        .iter()
        .find(|(alias, _)| *alias == normalized)
        .map_or(AnalysisDialect::Named(normalized), |(_, dialect)| {
            AnalysisDialect::Alias(dialect)
        })
}
