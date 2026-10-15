//! Failure text of one incomplete asset.

use crate::dagster_invocation::constants::SQL_INDENT;
use crate::dagster_invocation::models::AssetFailure;

/// `kind:name (status) [during phase]` with the error, staging relation and SQL indented below.
#[must_use]
pub fn asset_failure_text(failure: &AssetFailure) -> String {
    let mut first: String = format!("{}:{} ({})", failure.kind, failure.name, failure.status);
    if let Some(phase) = &failure.failed_phase {
        first.push_str(&format!(" during {phase}"));
    }
    let mut lines: Vec<String> = vec![first];
    if let Some(message) = &failure.error_message {
        let prefix: String = failure
            .error_code
            .as_ref()
            .map_or_else(String::new, |code| format!("[{code}] "));
        lines.push(format!("  {prefix}{message}"));
    }
    if let Some(relation) = &failure.staging_relation {
        lines.push(format!("  staging relation: {relation}"));
    }
    for (label, sql) in [
        ("  failed SQL:", &failure.failed_sql),
        ("  last recorded SQL:", &failure.last_recorded_sql),
    ] {
        if let Some(sql) = sql.as_ref().filter(|sql| !sql.is_empty()) {
            lines.push(label.to_owned());
            lines.push(indented(sql));
        }
    }
    lines.join("\n")
}

/// `textwrap.indent(text, SQL_INDENT)`: prefix every line that is not only whitespace.
fn indented(text: &str) -> String {
    text.split_inclusive('\n')
        .map(|line| {
            if line.trim().is_empty() {
                line.to_owned()
            } else {
                format!("{SQL_INDENT}{line}")
            }
        })
        .collect()
}
