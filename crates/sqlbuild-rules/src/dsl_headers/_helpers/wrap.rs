//! Description prose wrapped as Python's `textwrap.TextWrapper` wraps it, without breaking words.

use sqlbuild_core::text::main::python_isspace::python_isspace;

use crate::dsl_headers::_helpers::text::{chars, strip};

fn is_ascii_space(character: char) -> bool {
    matches!(character, '\t' | '\n' | '\u{b}' | '\u{c}' | '\r' | ' ')
}

/// `textwrap` lines of `text` under `width`, the first indented, never breaking words.
fn wrap_lines(text: &[char], width: usize, indent: &[char]) -> Vec<Vec<char>> {
    let mut chunks: Vec<&[char]> = Vec::new();
    let mut start: usize = 0;
    for index in 1..=text.len() {
        if index == text.len() || is_ascii_space(text[index]) != is_ascii_space(text[start]) {
            chunks.push(&text[start..index]);
            start = index;
        }
    }
    chunks.reverse();
    let is_blank = |chunk: &[char]| strip(chunk).is_empty();
    let mut lines: Vec<Vec<char>> = Vec::new();
    while !chunks.is_empty() {
        let line_indent: &[char] = if lines.is_empty() { indent } else { &[] };
        let available: usize = width.saturating_sub(line_indent.len());
        if chunks.last().is_some_and(|chunk| is_blank(chunk)) && !lines.is_empty() {
            chunks.pop();
        }
        let mut line: Vec<&[char]> = Vec::new();
        let mut length: usize = 0;
        while let Some(chunk) = chunks.last() {
            if length + chunk.len() > available {
                break;
            }
            length += chunk.len();
            line.extend(chunks.pop());
        }
        if line.is_empty()
            && let Some(chunk) = chunks.last()
            && chunk.len() > available
        {
            line.extend(chunks.pop());
        }
        if line.last().is_some_and(|chunk| is_blank(chunk)) {
            line.pop();
        }
        if !line.is_empty() {
            let mut rendered: Vec<char> = line_indent.to_vec();
            rendered.extend(line.concat());
            lines.push(rendered);
        }
    }
    lines
}

/// Offsets of `\n\s*\n` paragraph separators, as `re.split` finds them.
fn paragraphs(text: &[char]) -> Vec<&[char]> {
    let mut parts: Vec<&[char]> = Vec::new();
    let mut part_start: usize = 0;
    let mut index: usize = 0;
    while index < text.len() {
        if text[index] == '\n' {
            let mut run_end: usize = index + 1;
            while run_end < text.len() && python_isspace(text[run_end]) {
                run_end += 1;
            }
            if let Some(last) = text[index + 1..run_end].iter().rposition(|c| *c == '\n') {
                parts.push(&text[part_start..index]);
                part_start = index + 1 + last + 1;
                index = part_start;
                continue;
            }
        }
        index += 1;
    }
    parts.push(&text[part_start..]);
    parts
}

/// Description prose re-wrapped to the widths, keeping blank-line paragraph breaks.
pub(crate) fn wrap_description(description: &[char], first_width: i64, width: i64) -> Vec<char> {
    let normalized: Vec<char> =
        chars(&description.iter().collect::<String>().replace("\r\n", "\n"));
    let normalized: &[char] = strip(&normalized);
    let width_columns: usize = usize::try_from(width).unwrap_or(0);
    let mut wrapped: Vec<Vec<char>> = Vec::new();
    for (paragraph_index, paragraph) in paragraphs(normalized).into_iter().enumerate() {
        let words: Vec<&[char]> = paragraph
            .split(|character| python_isspace(*character))
            .filter(|word| !word.is_empty())
            .collect();
        let prose: Vec<char> = words.join(&' ');
        if prose.is_empty() {
            continue;
        }
        let first: i64 = if paragraph_index == 0 {
            first_width
        } else {
            width
        };
        let indent: Vec<char> = vec![' '; usize::try_from(width - first).unwrap_or(0)];
        let mut lines: Vec<Vec<char>> = wrap_lines(&prose, width_columns, &indent);
        if let Some(line) = lines.first_mut()
            && !indent.is_empty()
        {
            line.drain(..indent.len().min(line.len()));
        }
        wrapped.push(lines.join(&'\n'));
    }
    wrapped.join(&['\n', '\n'][..])
}
