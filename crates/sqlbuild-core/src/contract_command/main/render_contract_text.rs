//! The human contract comparison report.

use crate::contract_command::models::{ContractReport, ContractResourceText};

fn resource_lines(resource: &ContractResourceText) -> Vec<String> {
    let label: String = format!("{}:{}", resource.resource_type, resource.resource_name);
    if resource.findings.is_empty() {
        return vec![format!("  OK    {label}")];
    }
    let mut lines: Vec<String> = vec![format!("  DIFF  {label}")];
    lines.extend(
        resource
            .findings
            .iter()
            .map(|finding| format!("        {}: {}", finding.kind, finding.message)),
    );
    lines
}

/// Each resource as OK or DIFF with its findings, written files, and the difference count.
#[must_use]
pub fn render_contract_text(report: &ContractReport) -> String {
    let mut lines: Vec<String> = vec![format!(
        "Contract comparison from target '{}'",
        report.from_target
    )];
    for resource in &report.resources {
        lines.extend(resource_lines(resource));
    }
    if !report.written_paths.is_empty() {
        lines.push("\nUpdated repository declarations:".to_owned());
        lines.extend(report.written_paths.iter().map(|path| format!("  {path}")));
    }
    lines.push(format!(
        "\n{} contract difference(s)",
        report.difference_count()
    ));
    format!("{}\n", lines.join("\n"))
}
