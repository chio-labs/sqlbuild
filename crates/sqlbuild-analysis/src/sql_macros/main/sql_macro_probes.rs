use crate::sql_macros::_helpers::probes::{ProbePlan, probe_plan};
use crate::sql_macros::models::SqlMacroCheck;

/// The probe queries of the analysed model SQL `sql` that read each check's column types.
#[must_use]
pub fn sql_macro_probes(sql: &str, checks: &[SqlMacroCheck]) -> ProbePlan {
    probe_plan(sql, checks)
}
