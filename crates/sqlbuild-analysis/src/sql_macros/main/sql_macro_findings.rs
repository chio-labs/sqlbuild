use crate::sql_macros::_helpers::probes::{ProbePlan, check_findings};
use crate::sql_macros::models::{SqlMacroCheck, SqlMacroFinding};

/// Each argument the probes' columns show does not fit its parameter, in call order.
///
/// `results` holds each probe's `(column, type)` list, `None` where analysis knew none.
#[must_use]
pub fn sql_macro_findings(
    (plan, checks): (&ProbePlan, &[SqlMacroCheck]),
    results: &[Option<Vec<(String, Option<String>)>>],
    dialect: &str,
) -> Vec<SqlMacroFinding> {
    checks
        .iter()
        .zip(&plan.evidence)
        .flat_map(|(check, evidence)| check_findings((check, evidence), results, dialect))
        .collect()
}
