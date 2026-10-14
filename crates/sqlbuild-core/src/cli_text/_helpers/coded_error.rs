//! Result-stored coded errors, as CLI expected errors and compact inline rows render them.

use crate::cli_text::constants::MAX_INLINE_ERROR_LINES;
use crate::cli_text::models::CliStyle;
use crate::text::main::python_isspace::python_isspace;
use crate::text::main::python_splitlines::python_splitlines;
use crate::text::main::text_wrap::text_wrap;

/// `error[CODE]: message` or `[CODE] message`, later lines muted, then any help line.
pub(crate) fn coded_error(
    (code, message, help): (&str, &str, Option<&str>),
    include_error_label: bool,
    style: CliStyle,
) -> String {
    let mut lines = message.split('\n');
    let first: &str = lines.next().unwrap_or("");
    let rest: Vec<String> = lines.map(|line| style.muted(line)).collect();
    let rendered_message: String = if rest.is_empty() {
        message.to_owned()
    } else {
        format!("{first}\n{}", rest.join("\n"))
    };
    let mut rendered: String = format!(
        "{} {rendered_message}",
        style.error_strong(&if include_error_label {
            format!("error[{code}]:")
        } else {
            format!("[{code}]")
        })
    );
    if let Some(help) = help {
        rendered = format!("{rendered}\n  {} {help}", style.muted("= help:"));
    }
    rendered
}

/// `[code] message`, with `= help: help` on its own paragraph.
pub(crate) fn inline_error_text(code_prefix: &str, message: &str, help: Option<&str>) -> String {
    let text: String = if code_prefix.is_empty() {
        message.to_owned()
    } else {
        format!("{code_prefix} {message}")
    };
    match help {
        Some(help) => format!("{text}\n= help: {help}"),
        None => text,
    }
}

/// Every paragraph wrapped on whitespace only, an empty paragraph kept as one empty line.
pub(crate) fn wrap_paragraphs(text: &str, width: usize) -> Vec<String> {
    let mut paragraphs: Vec<&str> = python_splitlines(text);
    if paragraphs.is_empty() {
        paragraphs.push(text);
    }
    let mut wrapped: Vec<String> = Vec::new();
    for paragraph in paragraphs {
        let lines: Vec<String> = text_wrap(paragraph, width, ("", ""), false);
        if lines.is_empty() {
            wrapped.push(String::new());
        } else {
            wrapped.extend(lines);
        }
    }
    wrapped
}

/// The first lines, the last one cut to end in an ellipsis when lines were dropped.
pub(crate) fn truncate_lines(mut lines: Vec<String>, width: usize) -> Vec<String> {
    let truncated: bool = lines.len() > MAX_INLINE_ERROR_LINES;
    lines.truncate(MAX_INLINE_ERROR_LINES);
    if truncated && let Some(last) = lines.last_mut() {
        let ellipsis: String = ".".repeat(width.min(3));
        let kept: String = last
            .chars()
            .take(width.saturating_sub(ellipsis.len()))
            .collect();
        *last = format!("{}{ellipsis}", kept.trim_end_matches(python_isspace));
    }
    lines
}

/// The first occurrence of the code prefix in the first line, styled as strong error text.
pub(crate) fn style_code_prefix(
    mut lines: Vec<String>,
    code_prefix: &str,
    style: CliStyle,
) -> Vec<String> {
    if !code_prefix.is_empty()
        && let Some(first) = lines.first_mut()
    {
        *first = first.replacen(code_prefix, &style.error_strong(code_prefix), 1);
    }
    lines
}
