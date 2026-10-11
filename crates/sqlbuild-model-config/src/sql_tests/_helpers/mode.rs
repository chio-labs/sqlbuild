//! `_infer_sql_test_mode`: the mode named by a top-level direct-logic actual CTE.

use crate::sql_tests::constants::{ACTUAL_CTE_MARKER, ACTUAL_CTE_MODES, MODEL_MODE};
use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::main::is_python_word::is_python_word;

fn is_word(character: Option<&char>) -> bool {
    character.is_some_and(|character| {
        *character == '$' || is_python_word(active_python_text(), *character)
    })
}

fn find(text: &[char], from: usize, needle: &[char]) -> Option<usize> {
    (from..=text.len().saturating_sub(needle.len()))
        .find(|start| text[*start..].starts_with(needle))
}

/// The end of a `quote`-delimited token at `start`, with doubled quotes escaping when `doubled`.
fn quoted_end(text: &[char], start: usize, quote: char, doubled: bool) -> usize {
    let mut index = start + 1;
    while index < text.len() {
        if text[index] == quote {
            if doubled && text.get(index + 1) == Some(&quote) {
                index += 2;
                continue;
            }
            return index + 1;
        }
        index += 1;
    }
    text.len()
}

/// The end of a comment or quoted token at `index`, if one starts there.
fn skipped_end(text: &[char], index: usize) -> Option<usize> {
    match (text[index], text.get(index + 1)) {
        ('-', Some('-')) => Some(find(text, index, &['\n']).unwrap_or(text.len())),
        ('/', Some('*')) => {
            Some(find(text, index + 2, &['*', '/']).map_or(text.len(), |end| end + 2))
        }
        ('\'', _) => Some(quoted_end(text, index, '\'', true)),
        ('"', _) => Some(quoted_end(text, index, '"', true)),
        ('`', _) => Some(quoted_end(text, index, '`', false)),
        _ => None,
    }
}

fn skip_space(text: &[char], index: usize) -> usize {
    index
        + text[index..]
            .iter()
            .take_while(|character| is_python_space(**character))
            .count()
}

/// `(?i:AS)(?![\w$])` at `index`.
fn is_as(text: &[char], index: usize) -> bool {
    matches!(text.get(index), Some('a' | 'A'))
        && matches!(text.get(index + 1), Some('s' | 'S' | '\u{17f}'))
        && !is_word(text.get(index + 2))
}

/// `(?=\s*(?:\([^()]*\)\s*)?(?i:AS)(?![\w$]))` after a name ending at `end`.
fn defines_cte(text: &[char], end: usize) -> bool {
    let after_space = skip_space(text, end);
    if text.get(after_space) == Some(&'(') {
        let close = text[after_space + 1..]
            .iter()
            .position(|character| matches!(character, '(' | ')'))
            .map(|offset| after_space + 1 + offset);
        if let Some(close) = close.filter(|close| text[*close] == ')')
            && is_as(text, skip_space(text, close + 1))
        {
            return true;
        }
    }
    is_as(text, after_space)
}

/// The mode of an actual CTE name defined at `index`, and where the name ends.
fn actual_name(text: &[char], index: usize) -> Option<(&'static str, usize)> {
    if index > 0 && is_word(text.get(index - 1)) {
        return None;
    }
    ACTUAL_CTE_MODES.iter().find_map(|(name, mode)| {
        let name: Vec<char> = name.chars().collect();
        let end = index + name.len();
        (text[index..].starts_with(&name) && !is_word(text.get(end)) && defines_cte(text, end))
            .then_some((*mode, end))
    })
}

/// Each mode a top-level actual CTE names, in order of first definition.
pub(crate) fn defined_modes(sql: &str) -> Vec<&'static str> {
    if !sql.contains(ACTUAL_CTE_MARKER) {
        return vec![MODEL_MODE];
    }
    let text: Vec<char> = sql.chars().collect();
    let mut modes: Vec<&'static str> = Vec::new();
    let mut depth: usize = 0;
    let mut index = 0;
    while index < text.len() {
        if let Some(end) = skipped_end(&text, index) {
            index = end;
            continue;
        }
        match text[index] {
            '(' => depth += 1,
            ')' => depth = depth.saturating_sub(1),
            _ => {
                if let Some((mode, end)) = actual_name(&text, index) {
                    if depth == 0 && !modes.contains(&mode) {
                        modes.push(mode);
                    }
                    index = end;
                    continue;
                }
            }
        }
        index += 1;
    }
    if modes.is_empty() {
        modes.push(MODEL_MODE);
    }
    modes
}
