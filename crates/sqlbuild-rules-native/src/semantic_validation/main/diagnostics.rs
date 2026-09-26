use crate::semantic_validation::types::DiagnosticRow;

pub(crate) fn binding_diagnostics(
    sql: &str,
    dialect: &str,
    rows: Vec<DiagnosticRow>,
) -> Result<Vec<DiagnosticRow>, String> {
    crate::semantic_validation::_helpers::diagnostics::binding_diagnostics(sql, dialect, rows)
}
