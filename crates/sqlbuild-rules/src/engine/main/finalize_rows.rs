use crate::models::{Fault, RulesConfig};

/// Apply the exception policy once to completed built-in, SQL and custom findings.
pub fn finalize_rows(
    project_dir: String,
    config: RulesConfig,
    evaluated_codes: &[String],
    findings: Vec<Fault>,
) -> Result<Vec<Fault>, String> {
    crate::engine::_helpers::evaluation::finalize_findings(
        project_dir,
        config,
        evaluated_codes,
        findings,
    )
}
