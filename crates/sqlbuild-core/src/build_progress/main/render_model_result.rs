//! The persistent row of a finished model with its batch, hook, test and audit rows.

use crate::build_progress::_helpers::error_rows::error_detail;
use crate::build_progress::_helpers::model_rows::{
    SubRows, batch_lines, model_line, nested_rows, verbose_blocks,
};
use crate::build_progress::_helpers::rows::prefix_width;
use crate::build_progress::constants::{FAILED, SUB_INDENT};
use crate::build_progress::models::{
    ModelResultText, ModelRowFacts, ProgressLayout, TestResultText,
};
use crate::cli_text::models::CliStyle;

/// The model row at `counter` and every row nested under it.
#[must_use]
pub fn render_model_result(
    (model, facts, tests): (&ModelResultText, &ModelRowFacts, &[TestResultText]),
    counter: usize,
    layout: ProgressLayout,
    style: CliStyle,
) -> String {
    let mut text: String = model_line((model, facts), counter, layout, style);
    if layout.verbose {
        text.push_str(&verbose_blocks(model, facts, style));
    }
    text.push_str(&batch_lines(model, style));
    let sub: SubRows = SubRows {
        pad: " ".repeat(prefix_width(layout) + SUB_INDENT),
        name_width: layout.name_width.saturating_sub(SUB_INDENT),
        style,
    };
    text.push_str(&nested_rows(model, tests, &sub, layout.verbose));
    if model.status == FAILED
        && let Some(message) = model.error.message.as_deref().filter(|m| !m.is_empty())
    {
        text.push_str(&error_detail(
            (&model.error, message),
            (prefix_width(layout), layout.columns),
            false,
            style,
        ));
    }
    text
}
