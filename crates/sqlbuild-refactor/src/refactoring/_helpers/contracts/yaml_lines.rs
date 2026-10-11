//! Line-based YAML source declaration reads, as contract adoption's `edit_source` makes them.

use sqlbuild_core::text::main::python_splitlines::python_splitlines;
use sqlbuild_core::text::main::python_strip::python_strip;

use crate::refactoring::constants::{
    CONTRACT_QUOTES, CONTRACT_YAML_COMMENT, CONTRACT_YAML_LIST_NAME,
};

/// Python's `_indent`: the leading spaces of a line, in code points.
pub(crate) fn indent(line: &str) -> usize {
    line.chars()
        .take_while(|character| *character == ' ')
        .count()
}

fn unquote(value: &str) -> &str {
    let mut characters = value.chars();
    match (characters.next(), characters.next_back()) {
        (Some(first), Some(last)) if first == last && CONTRACT_QUOTES.contains(&first) => {
            &value[first.len_utf8()..value.len() - last.len_utf8()]
        }
        _ => value,
    }
}

/// Python's `_yaml_list_name`: the unquoted name of a `- name:` line.
pub(crate) fn list_name(line: &str) -> Option<&str> {
    python_strip(line)
        .strip_prefix(CONTRACT_YAML_LIST_NAME)
        .map(|rest| unquote(python_strip(rest)))
}

/// Python's `_yaml_key`: the key of a `key: value` line.
pub(crate) fn key(line: &str) -> Option<&str> {
    let stripped = python_strip(line);
    if stripped.is_empty() || stripped.starts_with(['#', '-']) {
        return None;
    }
    stripped.split_once(':').map(|(key, _)| python_strip(key))
}

/// Python's `_yaml_named_block`: the one shallowest `- name: <name>` block.
pub(crate) fn named_block(lines: &[&str], name: &str) -> Option<(usize, usize, usize)> {
    let matches: Vec<(usize, usize)> = lines
        .iter()
        .enumerate()
        .filter(|(_, line)| list_name(line) == Some(name))
        .map(|(index, line)| (index, indent(line)))
        .collect();
    let minimum = matches.iter().map(|(_, indent)| *indent).min()?;
    let candidates: Vec<usize> = matches
        .iter()
        .filter(|(_, indent)| *indent == minimum)
        .map(|(index, _)| *index)
        .collect();
    let [start] = candidates[..] else {
        return None;
    };
    let end = (start + 1..lines.len())
        .find(|index| indent(lines[*index]) <= minimum && list_name(lines[*index]).is_some())
        .unwrap_or(lines.len());
    Some((start, end, minimum))
}

fn is_blank_or_comment(line: &str) -> bool {
    let stripped = python_strip(line);
    stripped.is_empty() || stripped.starts_with('#')
}

/// Python's `_yaml_sequence_indent`: the indent of the first `- name:` item under a key.
pub(crate) fn sequence_indent(
    lines: &[&str],
    range: (usize, usize),
    key_indent: usize,
) -> Option<usize> {
    for line in &lines[range.0..range.1] {
        if is_blank_or_comment(line) {
            continue;
        }
        let line_indent = indent(line);
        if list_name(line).is_some() && line_indent >= key_indent {
            return Some(line_indent);
        }
        if line_indent <= key_indent {
            return None;
        }
    }
    None
}

/// Whether a line is neither blank nor a comment, as the columns-block scan reads it.
pub(crate) fn is_content(line: &str) -> bool {
    !is_blank_or_comment(line)
}

/// Python's `_yaml_comment`: a trailing ` #` comment without its line breaks.
pub(crate) fn comment(line: &str) -> &str {
    line.find(CONTRACT_YAML_COMMENT)
        .map_or("", |marker| line[marker..].trim_end_matches('\n'))
}

/// Python's `_yaml_string`: a single-quoted YAML scalar.
pub(crate) fn yaml_string(value: &str) -> String {
    format!("'{}'", value.replace('\'', "''"))
}

/// Python's `_yaml_column_lines`.
pub(crate) fn column_lines(name: &str, column_type: &str, indent: usize) -> Vec<String> {
    vec![
        format!("{}- name: {name}\n", " ".repeat(indent)),
        format!(
            "{}type: {}\n",
            " ".repeat(indent + 2),
            yaml_string(column_type)
        ),
    ]
}

/// Python's `str.splitlines(keepends=True)`: the lines of `text` with their breaks.
pub(crate) fn lines_with_breaks(text: &str) -> Vec<String> {
    let base = text.as_ptr() as usize;
    let starts: Vec<usize> = python_splitlines(text)
        .iter()
        .map(|line| line.as_ptr() as usize - base)
        .collect();
    starts
        .iter()
        .enumerate()
        .map(|(index, start)| {
            text[*start..starts.get(index + 1).copied().unwrap_or(text.len())].to_owned()
        })
        .collect()
}
