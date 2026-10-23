//! Origin compatibility policy entry point.

use crate::migrations::models::CompatibilityFinding;

/// Return blocking schema findings in their original order.
pub fn compatibility_findings(
    findings: &[CompatibilityFinding],
    policy: (&str, bool),
    dialect: &str,
) -> Result<Vec<String>, String> {
    crate::migrations::_helpers::decisions::compatibility::compatibility_findings(
        findings, policy, dialect,
    )
}
