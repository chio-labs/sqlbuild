//! The rules phase completion line.

use crate::rule_results::main::format_skipped_rules::format_skipped_rules;

/// The rules phase wall time first, then built-in and custom rule time, with the skipped note.
pub fn format_rules_progress(
    elapsed_seconds: f64,
    (built_in_ms, custom_ms): (i64, i64),
    skipped_rules: Option<&[String]>,
) -> String {
    let message: String = format!(
        "Evaluated rules. ({elapsed_seconds:.2}s; built-in {:.2}s, custom {:.2}s)",
        built_in_ms as f64 / 1000.0,
        custom_ms as f64 / 1000.0
    );
    match skipped_rules.and_then(format_skipped_rules) {
        Some(note) => format!("{message}; {note}"),
        None => message,
    }
}
