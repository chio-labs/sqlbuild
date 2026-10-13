//! Human `sqb debug` output.

use crate::cli_text::models::CliStyle;
use crate::debug_report::constants::HEADER;
use crate::debug_report::models::{DebugLine, DebugReport};

fn section(name: &str, (entries, style): (&[DebugLine], CliStyle)) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    lines.push(style.section(&format!("{name}:")));
    for line in entries {
        let mut message: String = line.message.clone();
        if let Some(status) = line.status {
            let status_message: &str = line.status_message.as_deref().unwrap_or(&line.message);
            let rendered: String = style.status_text(
                status.label(),
                &format!("[{} {status_message}]", status.label()),
            );
            message = if message.is_empty() {
                rendered
            } else {
                format!("{message} {rendered}")
            };
        }
        lines.push(format!("  {}: {message}", line.label));
    }
    lines.push(String::new());
    lines
}

/// The report as sectioned `label: message [STATUS detail]` lines.
#[must_use]
pub fn format_debug_text(report: &DebugReport, style: CliStyle) -> String {
    let mut lines: Vec<String> = vec![String::new(), style.title(HEADER), String::new()];
    lines.extend(section("Runtime", (&report.runtime, style)));
    lines.extend(section("Configuration", (&report.configuration, style)));
    lines.extend(section("Providers", (&report.providers, style)));
    lines.extend(section("Connection", (&report.connection, style)));
    lines.join("\n") + "\n"
}
