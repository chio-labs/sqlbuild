use crate::sql_macros::_helpers::probes::analysed_probes;
use crate::sql_macros::_helpers::probes::{check_findings, probe_plan};
use crate::sql_macros::models::{SqlMacroCheck, SqlMacroFinding};
use crate::sql_macros::types::RelationShapes;

/// Each call argument the analysed model SQL shows does not fit its parameter, in call order.
#[must_use]
pub fn check_sql_macro_arguments(
    dialect: &str,
    (sql, schema): (&str, &RelationShapes),
    checks: &[SqlMacroCheck],
) -> Vec<SqlMacroFinding> {
    let plan = probe_plan(sql, checks);
    if plan.probes.is_empty() {
        return Vec::new();
    }
    let Some(results) = analysed_probes(dialect, &plan.probes, schema) else {
        return Vec::new();
    };
    checks
        .iter()
        .zip(&plan.evidence)
        .flat_map(|(check, evidence)| check_findings((check, evidence), &results, dialect))
        .collect()
}
