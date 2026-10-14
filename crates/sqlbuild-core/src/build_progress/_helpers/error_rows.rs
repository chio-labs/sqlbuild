//! Inline error rows under progress lines and error blocks of the failure summary.

use crate::build_progress::constants::TYPE_WIDTH;
use crate::build_progress::models::ErrorText;
use crate::cli_text::main::format_coded_error::format_coded_error;
use crate::cli_text::main::format_inline_error_lines::format_inline_error_lines;
use crate::cli_text::main::format_tree_connector::format_tree_connector;
use crate::cli_text::models::CliStyle;
use crate::text::main::python_splitlines::python_splitlines;

/// The `error` label and wrapped message under a row, optionally drawn as a tree child.
pub(crate) fn error_detail(
    (error, message): (&ErrorText, &str),
    (prefix_width, columns): (usize, usize),
    tree_child: bool,
    style: CliStyle,
) -> String {
    let pad: String = " ".repeat(prefix_width + if tree_child { 4 } else { 0 });
    let connector_suffix: String = if tree_child {
        format!("{} ", format_tree_connector(style, true))
    } else {
        String::new()
    };
    let label_width: usize = if tree_child {
        TYPE_WIDTH - 3
    } else {
        TYPE_WIDTH - 1
    };
    let label: String = format!(
        "{}{}",
        style.error_muted("error"),
        " ".repeat(label_width.saturating_sub("error".len()))
    );
    let plain_prefix_width: usize = pad.len() + if tree_child { 4 } else { 0 } + label_width + 1;
    let content_width: usize = (columns as i64 - plain_prefix_width as i64).max(1) as usize;
    let lines: Vec<String> = format_inline_error_lines(
        (error.code.as_deref(), message, error.help.as_deref()),
        content_width,
        style,
    );
    let continuation: String = " ".repeat(plain_prefix_width);
    let mut text: String = String::new();
    for (index, line) in lines.iter().enumerate() {
        if index == 0 {
            text.push_str(&format!("{pad}{connector_suffix}{label} {line}\n"));
        } else {
            text.push_str(&format!("{continuation}{line}\n"));
        }
    }
    text
}

/// The labelled, indented error block of one failure summary entry.
pub(crate) fn failure_error_block(
    (code, message, help): (Option<&str>, &str, Option<&str>),
    style: CliStyle,
) -> Vec<String> {
    let label: String = format!(
        "{}{}",
        style.error_muted("error"),
        " ".repeat(TYPE_WIDTH - "error".len())
    );
    let rendered: String = match code {
        None => message.to_owned(),
        Some(code) => format_coded_error((code, message, help), false, style),
    };
    let mut lines: Vec<&str> = python_splitlines(&rendered);
    if lines.is_empty() {
        lines.push(&rendered);
    }
    lines
        .iter()
        .enumerate()
        .map(|(index, line)| {
            let display_label: String = if index == 0 {
                label.clone()
            } else {
                " ".repeat(TYPE_WIDTH)
            };
            format!("    {display_label}{line}")
        })
        .collect()
}
