//! The canonical layout of a header description: one line when it fits, else a `"""` block.

use sqlbuild_sqltext::header_strings::constants::{PARAGRAPH_BREAK, TRIPLE_QUOTE};
use sqlbuild_sqltext::header_strings::main::prose_string::prose_string;

use crate::dsl_headers::_helpers::quoted::description_value_span;
use crate::dsl_headers::_helpers::text::{
    chars, find, line_count, rfind_before, rstrip, slice, string, tail,
};
use crate::dsl_headers::_helpers::wrap::wrap_description;
use crate::dsl_headers::constants::HEADER_INDENT;

/// The span of the top-level `description` string, from its opening to past its closing quote.
pub(crate) fn description_string_span(header_text: &[char]) -> Option<(usize, usize)> {
    let (value_start, _) = description_value_span(header_text)?;
    let start: usize = value_start - 1;
    let Ok(prose) = prose_string(header_text, start) else {
        return None;
    };
    Some((start, prose.end))
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

/// The canonical text of the description string at `span`, or `None` if none stores `value`.
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
    let suffix: usize = closing_width(slice(header_text, end, line_end));
    let indent: String = header_text[line_start..start]
        .iter()
        .take_while(|character| matches!(character, ' ' | '\t'))
        .collect();
    if value.contains(TRIPLE_QUOTE) {
        return None;
    }
    let after: &[char] = tail(header_text, end);
    let one_line: Option<String> = (!value.contains('\n')).then(|| {
        let double: String = format!("\"{value}\"");
        if !value.contains('"') && stores_in_place(&double, value, after) {
            double
        } else {
            format!("{TRIPLE_QUOTE}{value}{TRIPLE_QUOTE}")
        }
    });
    let rendered: String = match one_line {
        Some(line) if prefix + line.chars().count() + suffix <= width => line,
        _ => block(value, &indent, width),
    };
    stores_in_place(&rendered, value, after).then_some(rendered)
}

/// The width a description's line adds after it: its separator, plus closing brackets that end it.
pub(crate) fn closing_width(rest: &[char]) -> usize {
    let rest: &[char] = rstrip(rest);
    if rest
        .iter()
        .all(|character| matches!(character, ',' | ')' | ';' | ' ' | '\t'))
    {
        return rest.len();
    }
    let spaces: usize = rest
        .iter()
        .take_while(|character| matches!(character, ' ' | '\t'))
        .count();
    if rest.get(spaces) == Some(&',') {
        spaces + 1
    } else {
        0
    }
}

/// Whether `rendered`, followed by the header text `after` it, reads as exactly `value`.
fn stores_in_place(rendered: &str, value: &str, after: &[char]) -> bool {
    let rendered: Vec<char> = chars(rendered);
    let followed: Vec<char> = [rendered.as_slice(), after].concat();
    prose_string(&followed, 0)
        .is_ok_and(|stored| stored.end == rendered.len() && stored.value == value)
}

/// The lines the description-length rule counts for `value` at `span` of `header_text`.
pub(crate) fn prose_length(
    value: &str,
    header_text: &[char],
    (start, end): (usize, usize),
    line_width: i64,
) -> usize {
    match canonical_prose(value, header_text, (start, end), line_width) {
        Some(rendered) if !rendered.contains('\n') => 1,
        _ => {
            let line_start: usize =
                rfind_before(header_text, '\n', start).map_or(0, |found| found + 1);
            let line_end: usize = find(header_text, &['\n'], end).unwrap_or(header_text.len());
            let prefix: i64 = i64::try_from(start + 1 - line_start).unwrap_or(i64::MAX);
            let suffix: i64 = i64::try_from(rstrip(slice(header_text, end, line_end)).len() + 1)
                .unwrap_or(i64::MAX);
            line_count(&wrap_description(
                &chars(value),
                (line_width - prefix - suffix).max(1),
                (line_width - suffix).max(1),
            ))
        }
    }
}
