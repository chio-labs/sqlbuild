//! The canonical layout of a header description: one line when it fits, else a `"""` block.

use sqlbuild_sqltext::header_strings::constants::{PARAGRAPH_BREAK, TRIPLE_QUOTE};
use sqlbuild_sqltext::header_strings::main::prose_string::prose_string;

use crate::dsl_headers::_helpers::quoted::description_value_span;
use crate::dsl_headers::_helpers::text::{chars, find, rfind_before, rstrip, slice, string};
use crate::dsl_headers::constants::HEADER_INDENT;

/// The span of the top-level `description` string, from its opening to past its closing quote.
pub(crate) fn description_string_span(header_text: &[char]) -> Option<(usize, usize)> {
    let (value_start, _) = description_value_span(header_text)?;
    let start: usize = value_start - 1;
    let end: usize = prose_string(header_text, start).ok()?.end;
    Some((start, end))
}

/// The breaks of one paragraph: lines filled to `width`, broken only at single spaces.
fn paragraph_lines(paragraph: &str, width: usize) -> Vec<String> {
    let characters: Vec<char> = paragraph.chars().collect();
    let mut words: Vec<String> = Vec::new();
    let mut word_start: usize = 0;
    for index in 1..characters.len().saturating_sub(1) {
        if characters[index] == ' ' && characters[index - 1] != ' ' && characters[index + 1] != ' '
        {
            words.push(string(&characters[word_start..index]));
            word_start = index + 1;
        }
    }
    words.push(string(&characters[word_start..]));
    let mut lines: Vec<String> = Vec::new();
    let mut line: String = String::new();
    for word in words {
        if !line.is_empty() && line.chars().count() + 1 + word.chars().count() > width {
            lines.push(std::mem::take(&mut line));
        }
        if !line.is_empty() {
            line.push(' ');
        }
        line.push_str(&word);
    }
    lines.push(line);
    lines
}

/// `value` as an indented `"""` block whose closing delimiter lines up with `indent`.
fn block(value: &str, indent: &str, line_width: usize) -> String {
    let content_indent: String = format!("{indent}{HEADER_INDENT}");
    let width: usize = line_width
        .saturating_sub(content_indent.chars().count())
        .max(1);
    let mut lines: Vec<String> = Vec::new();
    for (index, paragraph) in value.split(PARAGRAPH_BREAK).enumerate() {
        if index > 0 {
            lines.push(String::new());
        }
        lines.extend(
            paragraph_lines(paragraph, width)
                .into_iter()
                .map(|line| format!("{content_indent}{line}")),
        );
    }
    format!(
        "{TRIPLE_QUOTE}\n{}\n{indent}{TRIPLE_QUOTE}",
        lines.join("\n")
    )
}

/// The canonical text of the description string at `span` of `header_text`, holding `value`.
///
/// Text without line breaks that fits on its line stays one line: `"..."`, or `"""..."""` when
/// it holds a double quote. Anything longer is an indented `"""` block wrapped at
/// `line_width`. `None` when no layout stores exactly `value`.
pub(crate) fn canonical_prose(
    value: &str,
    header_text: &[char],
    (start, end): (usize, usize),
    line_width: i64,
) -> Option<String> {
    let width: usize = usize::try_from(line_width).unwrap_or(0);
    let line_start: usize = rfind_before(header_text, '\n', start).map_or(0, |found| found + 1);
    let line_end: usize = find(header_text, &['\n'], end).unwrap_or(header_text.len());
    let prefix: usize = start - line_start;
    let suffix: usize = rstrip(slice(header_text, end, line_end)).len();
    let indent: String = header_text[line_start..start]
        .iter()
        .take_while(|character| matches!(character, ' ' | '\t'))
        .collect();
    if value.contains(TRIPLE_QUOTE) {
        return None;
    }
    let one_line: Option<String> = (!value.contains('\n')).then(|| {
        if value.contains('"') || value.ends_with('\\') {
            format!("{TRIPLE_QUOTE}{value}{TRIPLE_QUOTE}")
        } else {
            format!("\"{value}\"")
        }
    });
    let rendered: String = match one_line {
        Some(line) if prefix + line.chars().count() + suffix <= width => line,
        _ => block(value, &indent, width),
    };
    let stored: String = prose_string(&chars(&rendered), 0).ok()?.value;
    (stored == value).then_some(rendered)
}

/// The physical lines a canonical description takes: one, or the lines of its block.
pub(crate) fn prose_line_count(rendered: &str) -> usize {
    if rendered.contains('\n') {
        rendered.lines().count().saturating_sub(2).max(1)
    } else {
        1
    }
}
