//! A completed grouped item with its tree of child rows and inline error.

use crate::cli_text::main::format_inline_error_lines::format_inline_error_lines;
use crate::cli_text::main::format_tree_connector::format_tree_connector;
use crate::cli_text::models::CliStyle;
use crate::nested_progress::constants::{
    CHILD_NAME_INDENT, ERROR_CONNECTOR_WIDTH, ERROR_PAD, LABEL_WIDTH,
};
use crate::nested_progress::models::{NestedItem, NestedLayout};

/// The item row, one tree row per child, and the error as the last tree child.
#[must_use]
pub fn render_nested_item(item: &NestedItem, layout: &NestedLayout, style: CliStyle) -> String {
    let width: usize = layout.name_width;
    let mut text: String = format!(
        "    {:<LABEL_WIDTH$}{:<width$} {}{}\n",
        layout.label,
        item.item_name,
        style.status(&item.status_text),
        item.detail
    );
    let child_width: usize = width.saturating_sub(CHILD_NAME_INDENT);
    let child_label_width: usize = LABEL_WIDTH - 2;
    for (index, child) in item.child_rows.iter().enumerate() {
        let last: bool = index + 1 == item.child_rows.len() && item.error.message.is_none();
        text.push_str(&format!(
            "      {} {:<child_label_width$}{:<child_width$} {}{}\n",
            format_tree_connector(style, last),
            child.label,
            child.name,
            style.status(&child.status_text),
            child.detail
        ));
    }
    let Some(message) = &item.error.message else {
        return text;
    };
    let label: String = style.error_muted(&format!("{:<child_label_width$}", "error"));
    let prefix_width: usize = ERROR_PAD.len() + ERROR_CONNECTOR_WIDTH + child_label_width;
    let content_width: usize = (layout.columns as i64 - prefix_width as i64).max(1) as usize;
    let lines: Vec<String> = format_inline_error_lines(
        (
            item.error.code.as_deref(),
            message,
            item.error.help.as_deref(),
        ),
        content_width,
        style,
    );
    let connector: String = format_tree_connector(style, true);
    for (index, line) in lines.iter().enumerate() {
        if index == 0 {
            text.push_str(&format!("{ERROR_PAD}{connector} {label}{line}\n"));
        } else {
            text.push_str(&format!("{}{line}\n", " ".repeat(prefix_width)));
        }
    }
    text
}
