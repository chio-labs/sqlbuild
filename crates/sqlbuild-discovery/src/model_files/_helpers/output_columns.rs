//! Python's lexical scan of the top-level SELECT list for authored output column locations.

use crate::model_files::_helpers::locations::{absolute_span, line_starts};
use crate::models::LineColumnSpan;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::main::is_python_word::is_python_word;
use sqlbuild_core::text::models::PythonText;

const SELECT_KEYWORD: &str = "SELECT";
const UNION_KEYWORD: &str = "UNION";
const FROM_KEYWORD: &str = "FROM";
const ESCAPE: char = '\\';

/// Python's `matched_model_output_column_locations` from the SQL start (a byte offset).
pub(crate) fn output_column_locations(
    python: PythonText,
    contents: &str,
    sql_start: usize,
    extract_implicit_alias_columns: bool,
) -> Vec<(String, LineColumnSpan)> {
    let characters: Vec<char> = contents.chars().collect();
    let sql_offset = contents[..sql_start].chars().count();
    let sql = &characters[sql_offset..];
    let Some((list_start, list_end)) = top_level_select_list_bounds(python, sql) else {
        return Vec::new();
    };
    let starts = line_starts(&characters);
    let mut locations: Vec<(String, LineColumnSpan)> = Vec::new();
    for (item_start, item_end) in split_top_level_items(sql, list_start, list_end) {
        let Some(name) =
            item_output_name(&sql[item_start..item_end], extract_implicit_alias_columns)
        else {
            continue;
        };
        let mut start = item_start;
        while start < item_end && is_python_space(sql[start]) {
            start += 1;
        }
        let mut end = item_end;
        while end > start && is_python_space(sql[end - 1]) {
            end -= 1;
        }
        if start >= end {
            continue;
        }
        locations.push((
            name,
            absolute_span(sql_offset + start, sql_offset + end, &starts),
        ));
    }
    locations
}

fn is_scan_special(character: char) -> bool {
    matches!(
        character,
        '\'' | '"' | '`' | '(' | ')' | 's' | 'S' | 'f' | 'F' | 'u' | 'U'
    )
}

fn top_level_select_list_bounds(python: PythonText, sql: &[char]) -> Option<(usize, usize)> {
    let length = sql.len();
    let has_union_candidate = contains_lowercase_union(sql);
    let (mut depth, mut index) = (0_usize, 0_usize);
    let (mut list_start, mut list_end): (Option<usize>, Option<usize>) = (None, None);
    let mut in_quote: Option<char> = None;
    while index < length {
        if in_quote.is_none() {
            match sql[index..]
                .iter()
                .position(|character| is_scan_special(*character))
            {
                Some(offset) => index += offset,
                None => break,
            }
        }
        let character = sql[index];
        if let Some(quote) = in_quote {
            if character == ESCAPE {
                index += 2;
                continue;
            }
            if character == quote {
                in_quote = None;
            }
            index += 1;
            continue;
        }
        if matches!(character, '\'' | '"') {
            in_quote = Some(character);
            index += 1;
            continue;
        }
        if character == '(' {
            depth += 1;
            index += 1;
            continue;
        }
        if character == ')' {
            depth = depth.saturating_sub(1);
            index += 1;
            continue;
        }
        if depth != 0 {
            index += 1;
            continue;
        }
        let upper = character.to_ascii_uppercase();
        match list_start {
            None => {
                if upper == 'S' && keyword_at(python, sql, SELECT_KEYWORD, index) {
                    index += SELECT_KEYWORD.len();
                    list_start = Some(index);
                    continue;
                }
            }
            Some(start) => {
                if upper == 'U' && keyword_at(python, sql, UNION_KEYWORD, index) {
                    return None;
                }
                if list_end.is_none()
                    && upper == 'F'
                    && keyword_at(python, sql, FROM_KEYWORD, index)
                {
                    list_end = Some(index);
                    if !has_union_candidate {
                        return Some((start, index));
                    }
                }
            }
        }
        index += 1;
    }
    list_start.map(|start| (start, list_end.unwrap_or(length)))
}

/// Python's `"union" in sql.lower()`; only `İ` and the Kelvin sign lower to ASCII letters.
fn contains_lowercase_union(sql: &[char]) -> bool {
    let mut lowered: Vec<char> = Vec::with_capacity(sql.len());
    for character in sql {
        match character {
            '\u{130}' => lowered.extend(['i', '\u{307}']),
            '\u{212a}' => lowered.push('k'),
            other if other.is_ascii() => lowered.push(other.to_ascii_lowercase()),
            _ => lowered.push('\u{fffd}'),
        }
    }
    lowered
        .windows(5)
        .any(|window| window == ['u', 'n', 'i', 'o', 'n'])
}

/// Python's `str.upper()` of one character when that is a single ASCII character.
fn ascii_upper(character: char) -> Option<char> {
    match character {
        '\u{131}' => Some('I'),
        '\u{17f}' => Some('S'),
        other if other.is_ascii() => Some(other.to_ascii_uppercase()),
        _ => None,
    }
}

fn keyword_at(python: PythonText, sql: &[char], keyword: &str, index: usize) -> bool {
    let end = index + keyword.len();
    let slice = &sql[index..end.min(sql.len())];
    if slice.len() != keyword.len()
        || !slice
            .iter()
            .zip(keyword.chars())
            .all(|(character, expected)| ascii_upper(*character) == Some(expected))
    {
        return false;
    }
    let before = index.checked_sub(1).map_or(' ', |previous| sql[previous]);
    let after = sql.get(end).copied().unwrap_or(' ');
    !is_python_word(python, before) && !is_python_word(python, after)
}

fn split_top_level_items(sql: &[char], start: usize, end: usize) -> Vec<(usize, usize)> {
    let mut items: Vec<(usize, usize)> = Vec::new();
    let mut depth = 0_usize;
    let mut item_start = start;
    let mut index = start;
    let mut in_quote: Option<char> = None;
    while index < end {
        let character = sql[index];
        if let Some(quote) = in_quote {
            if character == ESCAPE {
                index += 2;
                continue;
            }
            if character == quote {
                in_quote = None;
            }
            index += 1;
            continue;
        }
        match character {
            '\'' | '"' => in_quote = Some(character),
            '(' => depth += 1,
            ')' => depth = depth.saturating_sub(1),
            ',' if depth == 0 => {
                items.push((item_start, index));
                item_start = index + 1;
            }
            _ => {}
        }
        index += 1;
    }
    items.push((item_start, end));
    items
}

/// Python's `_select_item_output_name`.
fn item_output_name(item: &[char], extract_implicit_alias_columns: bool) -> Option<String> {
    if let Some(name) = explicit_alias(item) {
        return Some(name);
    }
    if let Some(name) = bare_reference(item) {
        return Some(name);
    }
    if extract_implicit_alias_columns {
        return implicit_alias(item);
    }
    None
}

/// `[A-Za-z_]`, which also matches `İ`, `ı`, `ſ` and the Kelvin sign under `re.IGNORECASE`.
fn is_identifier_start(character: char, ignore_case: bool) -> bool {
    character.is_ascii_alphabetic()
        || character == '_'
        || (ignore_case && matches!(character, '\u{130}' | '\u{131}' | '\u{17f}' | '\u{212a}'))
}

fn is_identifier_continue(character: char, ignore_case: bool) -> bool {
    is_identifier_start(character, ignore_case) || character.is_ascii_digit()
}

/// `(?P<name>[A-Za-z_][A-Za-z0-9_]*|"[^"]+")` at `start`: the end of the name.
fn name_end(item: &[char], start: usize, ignore_case: bool) -> Option<usize> {
    let first = *item.get(start)?;
    if is_identifier_start(first, ignore_case) {
        let mut end = start + 1;
        while end < item.len() && is_identifier_continue(item[end], ignore_case) {
            end += 1;
        }
        return Some(end);
    }
    if first == '"'
        && item
            .get(start + 1)
            .is_some_and(|character| *character != '"')
    {
        let close = item[start + 1..]
            .iter()
            .position(|character| *character == '"')?;
        return Some(start + 1 + close + 1);
    }
    None
}

fn rest_is_space(item: &[char], start: usize) -> bool {
    item[start..]
        .iter()
        .all(|character| is_python_space(*character))
}

fn space_run_end(item: &[char], start: usize) -> usize {
    let mut end = start;
    while end < item.len() && is_python_space(item[end]) {
        end += 1;
    }
    end
}

fn captured_name(item: &[char], start: usize, end: usize) -> String {
    item[start..end]
        .iter()
        .collect::<String>()
        .trim_matches('"')
        .to_owned()
}

/// `re.search(r"\s+AS\s+NAME\s*\Z", item, re.IGNORECASE)`.
fn explicit_alias(item: &[char]) -> Option<String> {
    for start in 0..item.len() {
        if !is_python_space(item[start]) || (start > 0 && is_python_space(item[start - 1])) {
            continue;
        }
        let keyword = space_run_end(item, start);
        if !matches!(item.get(keyword), Some('a' | 'A'))
            || !matches!(item.get(keyword + 1), Some('s' | 'S' | '\u{17f}'))
        {
            continue;
        }
        let name_start = space_run_end(item, keyword + 2);
        if name_start == keyword + 2 {
            continue;
        }
        if let Some(end) = name_end(item, name_start, true)
            && rest_is_space(item, end)
        {
            return Some(captured_name(item, name_start, end));
        }
    }
    None
}

/// `re.match(r"\s*(?:(?:IDENT|QUOTED)\.)?NAME\s*\Z", item)`.
fn bare_reference(item: &[char]) -> Option<String> {
    let start = space_run_end(item, 0);
    if let Some(qualifier_end) = name_end(item, start, false)
        && item.get(qualifier_end) == Some(&'.')
        && let Some(end) = name_end(item, qualifier_end + 1, false)
        && rest_is_space(item, end)
    {
        return Some(captured_name(item, qualifier_end + 1, end));
    }
    let end = name_end(item, start, false)?;
    rest_is_space(item, end).then(|| captured_name(item, start, end))
}

/// `re.search(r"\)\s+NAME\s*\Z", item)`.
fn implicit_alias(item: &[char]) -> Option<String> {
    for (index, character) in item.iter().enumerate() {
        if *character != ')' {
            continue;
        }
        let name_start = space_run_end(item, index + 1);
        if name_start == index + 1 {
            continue;
        }
        if let Some(end) = name_end(item, name_start, false)
            && rest_is_space(item, end)
        {
            return Some(captured_name(item, name_start, end));
        }
    }
    None
}
