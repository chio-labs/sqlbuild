//! Task and asset result rows.

use crate::build_command::constants::{
    PYTHON_NODE_SKIPPED, PYTHON_NODE_SUCCESS, PYTHON_STATUS_FAIL, PYTHON_STATUS_OK,
    PYTHON_STATUS_SKIP,
};
use crate::build_command::models::PythonNodeRow;
use crate::cli_text::models::CliStyle;

/// `  python    <kind><name> <STATUS>`, then the error or skip reason.
#[must_use]
pub fn render_python_node_rows(rows: &[PythonNodeRow], style: CliStyle) -> String {
    let mut text: String = String::new();
    for row in rows {
        let status: &str = match row.status.as_str() {
            PYTHON_NODE_SUCCESS => PYTHON_STATUS_OK,
            PYTHON_NODE_SKIPPED => PYTHON_STATUS_SKIP,
            _ => PYTHON_STATUS_FAIL,
        };
        text.push_str(&format!(
            "  {:<10}{:<10}{:<50} {}",
            "python",
            row.kind,
            row.node_name,
            style.status(status)
        ));
        if let Some(message) = row
            .error_message
            .as_deref()
            .filter(|value| !value.is_empty())
        {
            text.push_str(&format!("  {message}"));
        } else if let Some(reason) = row.skip_reason.as_deref().filter(|value| !value.is_empty()) {
            text.push_str(&format!("  {reason}"));
        }
        text.push('\n');
    }
    text
}
