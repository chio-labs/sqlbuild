//! Python `re` semantics of the SQL-test text checks: `\w`, `\s` and `re.IGNORECASE` literals.

use std::collections::HashSet;

use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::main::is_python_word::is_python_word;
use sqlbuild_core::text::main::python_casefold::python_casefold;
use sqlbuild_core::text::main::python_ignorecase_key::python_ignorecase_key;
use sqlbuild_core::text::models::PythonText;

const DOLLAR: char = '$';
const QUOTE_CHARACTERS: [char; 2] = ['"', '`'];
const AS_KEYWORD: [char; 2] = ['a', 's'];
const OPEN_PAREN: char = '(';

/// One character of `[\w$]`.
fn identifier_character(python: PythonText, character: char) -> bool {
    character == DOLLAR || is_python_word(python, character)
}

/// The start of `[A-Za-z_]`.
fn identifier_start(character: char) -> bool {
    character.is_ascii_alphabetic() || character == '_'
}

/// `re.findall(r"[A-Za-z_][\w$]*", sql)` casefolded, each distinct token once, first first.
pub(crate) fn identifier_tokens(sql: &str) -> Vec<String> {
    let python: PythonText = active_python_text();
    let characters: Vec<char> = sql.chars().collect();
    let mut seen: HashSet<String> = HashSet::new();
    let mut tokens: Vec<String> = Vec::new();
    let mut index: usize = 0;
    while index < characters.len() {
        if !identifier_start(characters[index]) {
            index += 1;
            continue;
        }
        let start: usize = index;
        index += 1;
        while index < characters.len() && identifier_character(python, characters[index]) {
            index += 1;
        }
        let token: String = characters[start..index].iter().collect();
        let folded: String = python_casefold(python, &token);
        if seen.insert(folded.clone()) {
            tokens.push(folded);
        }
    }
    tokens
}

/// Whether `text[at..]` starts with `literal` under `re.IGNORECASE`.
fn ignorecase_at(python: PythonText, text: &[char], at: usize, literal: &[char]) -> bool {
    text.len() >= at + literal.len()
        && text[at..at + literal.len()]
            .iter()
            .zip(literal)
            .all(|(left, right)| {
                python_ignorecase_key(python, *left) == python_ignorecase_key(python, *right)
            })
}

/// Whether no `[\w$]` character precedes `at`.
fn starts_word(python: PythonText, text: &[char], at: usize) -> bool {
    at == 0 || !identifier_character(python, text[at - 1])
}

/// The first `at >= from` where `(?<![\w$])literal` matches under `re.IGNORECASE`.
fn word_start(python: PythonText, text: &[char], from: usize, literal: &[char]) -> Option<usize> {
    (from..=text.len().saturating_sub(literal.len()))
        .find(|at| starts_word(python, text, *at) && ignorecase_at(python, text, *at, literal))
}

/// `re.search(rf"(?<![\w$]){re.escape(word)}(?![\w$])", sql, re.IGNORECASE)`.
pub(crate) fn reads_word(sql: &str, word: &str) -> bool {
    let python: PythonText = active_python_text();
    let text: Vec<char> = sql.chars().collect();
    let literal: Vec<char> = word.chars().collect();
    (0..=text.len().saturating_sub(literal.len())).any(|at| {
        starts_word(python, &text, at)
            && ignorecase_at(python, &text, at, &literal)
            && text
                .get(at + literal.len())
                .is_none_or(|next| !identifier_character(python, *next))
    })
}

/// After a CTE name: an optional quote, `\s+AS\s*\(`; the index after `(`, if it matches.
fn cte_header_end(python: PythonText, text: &[char], at: usize) -> Option<usize> {
    let mut index: usize = at;
    if text
        .get(index)
        .is_some_and(|character| QUOTE_CHARACTERS.contains(character))
    {
        index += 1;
    }
    let spaces: usize = index;
    while index < text.len() && is_python_space(text[index]) {
        index += 1;
    }
    if index == spaces || !ignorecase_at(python, text, index, &AS_KEYWORD) {
        return None;
    }
    index += AS_KEYWORD.len();
    while index < text.len() && is_python_space(text[index]) {
        index += 1;
    }
    (text.get(index) == Some(&OPEN_PAREN)).then_some(index + 1)
}

/// `(?<![\w$])name["`]?\s+AS\s*\(` searched from `from` under `re.IGNORECASE`: start and end.
pub(crate) fn cte_header(text: &[char], from: usize, name: &[char]) -> Option<(usize, usize)> {
    let python: PythonText = active_python_text();
    let mut search: usize = from;
    while let Some(start) = word_start(python, text, search, name) {
        if let Some(end) = cte_header_end(python, text, start + name.len()) {
            return Some((start, end));
        }
        search = start + 1;
    }
    None
}

/// `re.search(re.escape(call), text, re.IGNORECASE)` from `from`.
pub(crate) fn literal_from(text: &[char], from: usize, literal: &[char]) -> Option<usize> {
    let python: PythonText = active_python_text();
    (from..=text.len().saturating_sub(literal.len()))
        .find(|at| ignorecase_at(python, text, *at, literal))
}
