//! `format_sql_bodies`: SQLBuild-owned safe formatting of every SQL body in files.

use crate::lint_text::_helpers::format_bodies::{RequestTable, prepare_file, splice_file};
use crate::lint_text::errors::LintTextError;
use crate::lint_text::models::{FormatFile, FormattedBodies, PreparedBody};
use crate::sql_lint::main::format_requests::format_requests;
use crate::sql_lint::models::FormatResponse;

/// Format SQL bodies, reporting every declined body as a fault and leaving it unchanged.
pub fn format_sql_bodies(
    files: &[FormatFile],
    dialect: &str,
    line_width: usize,
) -> Result<FormattedBodies, LintTextError> {
    let mut table: RequestTable = RequestTable::default();
    let mut prepared: Vec<Vec<PreparedBody>> = Vec::with_capacity(files.len());
    for file in files {
        let mut bodies: Vec<PreparedBody> = Vec::new();
        for (mut body, sql, widths) in prepare_file(file, dialect)? {
            body.request = table.insert(sql, widths, (dialect, line_width));
            bodies.push(body);
        }
        prepared.push(bodies);
    }
    let responses: Vec<FormatResponse> = format_requests(table.requests);
    let mut result: FormattedBodies = FormattedBodies::default();
    for (index, (file, bodies)) in files.iter().zip(prepared).enumerate() {
        let (formatted, faults) = splice_file(index, &file.contents, &bodies, &responses);
        result.formatted.extend(formatted.map(|text| (index, text)));
        result.faults.extend(faults);
    }
    Ok(result)
}
