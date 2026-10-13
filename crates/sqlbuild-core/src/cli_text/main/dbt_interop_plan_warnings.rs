//! The warnings a `sqb dbt` plan reports.

use crate::cli_text::constants::DBT_NO_MATCH_WARNING;

/// `warnings`, plus the no-match warning when neither dbt nor SQLBuild has work.
#[must_use]
pub fn dbt_interop_plan_warnings(warnings: Vec<String>, has_work: bool) -> Vec<String> {
    if has_work
        || warnings
            .iter()
            .any(|warning| warning == DBT_NO_MATCH_WARNING)
    {
        return warnings;
    }
    let mut warnings: Vec<String> = warnings;
    warnings.push(DBT_NO_MATCH_WARNING.to_owned());
    warnings
}
