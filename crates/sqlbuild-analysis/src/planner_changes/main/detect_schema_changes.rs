//! Compare declared and inferred columns with the warehouse relation's columns.

use std::collections::HashSet;

use crate::planner_changes::_helpers::schema_comparer::{Comparer, FoldedColumns, folded_columns};
use crate::planner_changes::models::{
    SchemaColumnSource, SchemaColumns, SchemaComparison, SchemaFindingRow,
};
use crate::planner_changes::types::SchemaChecks;

/// Findings in Python's order: declared and inferred columns, dynamic families, then removed columns.
pub fn detect_schema_changes<E>(
    columns: SchemaColumns,
    comparison: SchemaComparison,
    (types_equal, single_family_type): SchemaChecks<'_, E>,
) -> Result<Vec<SchemaFindingRow>, E> {
    let FoldedColumns {
        yml,
        inferred,
        warehouse,
    } = folded_columns(columns, comparison.case_folding);
    let mut comparer = Comparer {
        warehouse: &warehouse,
        seen: HashSet::new(),
        findings: Vec::new(),
        types_equal,
    };
    let inferred: &[(String, Option<String>)] = inferred.as_deref().unwrap_or_default();
    if comparison.type_enforcement {
        comparer.compare(&yml, SchemaColumnSource::Yml, false)?;
        comparer.compare(inferred, SchemaColumnSource::SqlAnalysis, true)?;
    } else {
        comparer.compare(inferred, SchemaColumnSource::SqlAnalysis, true)?;
        comparer.compare(&yml, SchemaColumnSource::Yml, true)?;
    }
    comparer.compare_families(single_family_type)?;
    if comparison.type_enforcement || comparison.inferred_schema_complete {
        comparer.report_removed(if yml.is_empty() {
            SchemaColumnSource::SqlAnalysis
        } else {
            SchemaColumnSource::Yml
        });
    }
    Ok(comparer.findings)
}
