//! The lookup records of a cached full index.

use crate::scope_cache::models::CachedIndex;
use crate::scope_index::models::{ReportDiagnosticKey, ReportRecords, ReportUsage};

/// The lookup's records of a full index.
#[must_use]
pub fn cached_report_records(index: &CachedIndex) -> ReportRecords {
    ReportRecords {
        roots: index.roots.clone(),
        resources: index.resources.clone(),
        declarations: index
            .declarations
            .iter()
            .map(|item| item.record.clone())
            .collect(),
        usages: index
            .usages
            .iter()
            .map(|item| ReportUsage {
                consumer: item.consumer.clone(),
                declaration: item.declaration.clone(),
                kind: item.kind.clone(),
                through: item.through.clone(),
            })
            .collect(),
        grants: index.grants.clone(),
        diagnostics: index
            .diagnostics
            .iter()
            .map(|item| ReportDiagnosticKey {
                path: item.path.clone(),
                line: item.line,
                column: item.column,
                code: item.code.clone(),
            })
            .collect(),
    }
}
