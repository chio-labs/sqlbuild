//! One dbt node row and its messages.

use crate::cli_text::main::format_aligned_name_value::format_aligned_name_value;
use crate::cli_text::models::{AlignedRow, CliStyle};
use crate::dbt_events::_helpers::rows::{counter, display_status, truncated};
use crate::dbt_events::constants::{
    COUNTER_WIDTH, DURATION_WIDTH, ERROR_LEVEL, MESSAGE_STATUS_WIDTH, NAME_WIDTH,
    RESOURCE_TYPE_WIDTH, STATUS_WIDTH, WARN_LEVEL,
};
use crate::dbt_events::models::{DbtNodeResult, DbtRowPosition};
use crate::text::main::python_isspace::python_isspace;

/// The row text with a trailing newline, then one line per node message.
#[must_use]
pub fn render_dbt_node_row(
    result: &DbtNodeResult,
    position: DbtRowPosition,
    detail: &str,
    style: CliStyle,
) -> String {
    let status: String = display_status(&result.status);
    let duration: String = result
        .execution_time
        .map_or_else(String::new, |seconds| format!("{seconds:.2}s"));
    let padding: String = " ".repeat(STATUS_WIDTH.saturating_sub(status.chars().count()));
    let rendered_detail: String = if detail.is_empty() {
        String::new()
    } else {
        style.muted(detail)
    };
    let value: String = format!(
        "{}{padding} {duration:<DURATION_WIDTH$}{rendered_detail}",
        style.status(&status)
    );
    let name: String = truncated(&result.node_name, NAME_WIDTH);
    let mut text: String = format!(
        "  {:<COUNTER_WIDTH$} {:<RESOURCE_TYPE_WIDTH$}",
        counter(result, position),
        truncated(&result.resource_type, RESOURCE_TYPE_WIDTH)
    );
    text.push_str(&format_aligned_name_value(&AlignedRow {
        plain_name: name.clone(),
        styled_name: name,
        value: value.trim_end_matches(python_isspace).to_owned(),
        name_column_width: NAME_WIDTH,
        prefix: " ".to_owned(),
    }));
    text.push('\n');
    for message in &result.messages {
        let level: &str = if message.level == WARN_LEVEL {
            WARN_LEVEL
        } else {
            ERROR_LEVEL
        };
        text.push_str(&format!(
            "         {:<MESSAGE_STATUS_WIDTH$} {}\n",
            style.status(level),
            message.message
        ));
    }
    text
}
