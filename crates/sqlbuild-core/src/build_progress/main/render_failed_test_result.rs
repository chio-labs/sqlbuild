//! A failing SQL test row written inline, with its expectations as tree children.

use crate::build_progress::_helpers::error_rows::error_detail;
use crate::build_progress::_helpers::rows::prefix_width;
use crate::build_progress::_helpers::text::{
    counter_width, pad, test_outcome_display, truncate_name,
};
use crate::build_progress::constants::{SUB_INDENT, TREE_CHILD_NAME_INDENT, TYPE_WIDTH};
use crate::build_progress::models::{ProgressLayout, TestResultText};
use crate::cli_text::main::format_tree_connector::format_tree_connector;
use crate::cli_text::models::CliStyle;
use crate::progress::main::format_expectation_name::format_expectation_name;

/// The test row without a position, its expectation rows and its error.
#[must_use]
pub fn render_failed_test_result(
    test: &TestResultText,
    layout: ProgressLayout,
    style: CliStyle,
) -> String {
    let mut text: String = format!(
        "  {}  {}{} {}\n",
        " ".repeat(counter_width(layout.total)),
        style.muted(&pad("test", TYPE_WIDTH)),
        pad(
            &truncate_name(&test.label, layout.name_width),
            layout.name_width
        ),
        style.status(test_outcome_display(&test.outcome))
    );
    let error: Option<&str> = test.error.message.as_deref().filter(|m| !m.is_empty());
    let expectation_pad: String = " ".repeat(prefix_width(layout) + SUB_INDENT + 2);
    let child_width: usize = layout.name_width.saturating_sub(TREE_CHILD_NAME_INDENT);
    for (index, step) in test.steps.iter().enumerate() {
        let last: bool = index + 1 == test.steps.len() && error.is_none();
        text.push_str(&format!(
            "{expectation_pad}{} {}{} {}{}\n",
            format_tree_connector(style, last),
            style.muted(&pad("expect", TYPE_WIDTH - 2)),
            pad(&format_expectation_name(&step.model_name), child_width),
            style.status(test_outcome_display(&step.outcome)),
            step.detail
        ));
    }
    if let Some(message) = error {
        text.push_str(&error_detail(
            (&test.error, message),
            (prefix_width(layout), layout.columns),
            true,
            style,
        ));
    }
    text
}
