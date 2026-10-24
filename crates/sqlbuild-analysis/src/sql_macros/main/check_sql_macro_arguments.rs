use crate::sql_macros::_helpers::typing::probes::{
    ProbePlan, analysed_probes, check_findings, probe_plan,
};
use crate::sql_macros::models::SqlMacroFinding;
use crate::sql_macros::types::{ArgumentCheckInput, ProbeColumns};

/// Each model's call arguments its analysed SQL shows do not fit.
#[must_use]
pub fn check_sql_macro_arguments(
    dialect: &str,
    models: &[ArgumentCheckInput<'_>],
) -> Vec<Vec<SqlMacroFinding>> {
    let plans: Vec<ProbePlan> = models
        .iter()
        .map(|(sql, _, checks)| probe_plan(sql, checks))
        .collect();
    let batch: Vec<(&[String], _)> = plans
        .iter()
        .zip(models)
        .map(|(plan, (_, schema, _))| (plan.probes.as_slice(), *schema))
        .collect();
    let results: Vec<Vec<ProbeColumns>> = analysed_probes(dialect, &batch);
    plans
        .iter()
        .zip(models)
        .zip(&results)
        .map(|((plan, (_, _, checks)), columns)| model_findings(plan, checks, columns, dialect))
        .collect()
}

fn model_findings(
    plan: &ProbePlan,
    checks: &[crate::sql_macros::models::SqlMacroCheck],
    columns: &[ProbeColumns],
    dialect: &str,
) -> Vec<SqlMacroFinding> {
    checks
        .iter()
        .zip(&plan.evidence)
        .flat_map(|(check, evidence)| check_findings((check, evidence), columns, dialect))
        .collect()
}
