//! `format_diagnostic_record`: one `--debug` stderr line for a Python log record.

use crate::cli_text::models::CliStyle;
use crate::diagnostic_text::_helpers::record_parts::{header, python_space};
use crate::diagnostic_text::constants::{INLINE_SQL_STATEMENTS, SQL_SEPARATOR_WIDTH};
use crate::diagnostic_text::models::DiagnosticRecordText;

/// The header, then any logged SQL inline or between separator rules; no exception text.
#[must_use]
pub fn format_diagnostic_record(record: &DiagnosticRecordText, style: CliStyle) -> String {
    let header: String = header(record, style);
    let Some(sql) = &record.sql else {
        return header;
    };
    let stripped: &str = sql.trim_matches(python_space);
    if INLINE_SQL_STATEMENTS.contains(&stripped.to_uppercase().as_str()) {
        return format!("{header}  {stripped}");
    }
    let separator: String = style.muted(&"-".repeat(SQL_SEPARATOR_WIDTH));
    format!(
        "{header}\n{separator}\n{}\n{separator}",
        sql.trim_end_matches(python_space)
    )
}
