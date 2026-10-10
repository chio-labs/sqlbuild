//! Python's semantic message rewriting and code-owned help texts.

use std::sync::LazyLock;

use regex::Regex;
use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::is_python_word::is_python_word;

use crate::semantic_checks::_helpers::sql_text::python_regex::ignorecase_equal;
use crate::semantic_checks::_helpers::sql_text::text::upper;
use crate::semantic_checks::constants::{
    BIGQUERY_DIALECT, COMPARISON_CODE, CONTEXT_SUFFIX_PATTERN, DATE_TYPE, MISSING_PATTERN,
    QUOTED_PIECE_PATTERN, SEMANTIC_HELP, TIMESTAMP_TYPE, TYPE_WORDS,
};
use crate::semantic_checks::models::SemanticFailure;

static MISSING: LazyLock<Result<Regex, String>> = LazyLock::new(|| compiled(MISSING_PATTERN));
static CONTEXT_SUFFIX: LazyLock<Result<Regex, String>> =
    LazyLock::new(|| compiled(&format!(r"{CONTEXT_SUFFIX_PATTERN}\z")));
static QUOTED_PIECE: LazyLock<Result<Regex, String>> =
    LazyLock::new(|| compiled(QUOTED_PIECE_PATTERN));

/// Compile one of this lane's constant patterns.
pub(crate) fn compiled(pattern: &str) -> Result<Regex, String> {
    Regex::new(pattern).map_err(|error| error.to_string())
}

/// A compiled constant pattern, or an internal failure if it did not compile.
pub(crate) fn pattern(
    compiled: &'static Result<Regex, String>,
) -> Result<&'static Regex, SemanticFailure> {
    compiled
        .as_ref()
        .map_err(|_| SemanticFailure::internal("a constant pattern does not compile"))
}

/// Python's `semantic_help`.
pub(crate) fn semantic_help(code: &str) -> Option<&'static str> {
    SEMANTIC_HELP
        .iter()
        .find(|(known, _)| *known == code)
        .map(|(_, help)| *help)
}

/// Python's `re.sub(r" \(context: [^)]*\)$", "", message)`: Python's `$` also matches before a
/// final newline, which the suffix then keeps.
fn without_context_suffix(message: &str) -> Result<String, SemanticFailure> {
    let suffix: &Regex = pattern(&CONTEXT_SUFFIX)?;
    let (body, newline) = match message.strip_suffix('\n') {
        Some(body) => (body, "\n"),
        None => (message, ""),
    };
    Ok(format!("{}{newline}", suffix.replace(body, "")))
}

/// Python's `sentence_message`: drop the context suffix and upper-case unquoted type words.
pub(crate) fn sentence_message(message: &str) -> Result<String, SemanticFailure> {
    let quoted: &Regex = pattern(&QUOTED_PIECE)?;
    let text: String = without_context_suffix(message)?;
    let mut sentence = String::with_capacity(text.len());
    let mut last: usize = 0;
    for piece in quoted.find_iter(&text) {
        sentence.push_str(&upper_type_words(&text[last..piece.start()]));
        sentence.push_str(piece.as_str());
        last = piece.end();
    }
    sentence.push_str(&upper_type_words(&text[last..]));
    Ok(sentence)
}

fn upper_type_words(text: &str) -> String {
    let characters: Vec<char> = text.chars().collect();
    let mut result = String::with_capacity(text.len());
    let mut last: usize = 0;
    for (start, end) in type_word_spans(&characters) {
        result.extend(&characters[last..start]);
        result.push_str(&upper(&characters[start..end].iter().collect::<String>()));
        last = end;
    }
    result.extend(&characters[last..]);
    result
}

/// Python's `re.finditer(_TYPE_WORDS, text, re.IGNORECASE)` spans, in code points.
fn type_word_spans(characters: &[char]) -> Vec<(usize, usize)> {
    let python = active_python_text();
    let word = |index: usize| {
        characters
            .get(index)
            .is_some_and(|character| is_python_word(python, *character))
    };
    let boundary = |index: usize| (index > 0 && word(index - 1)) != word(index);
    let mut spans: Vec<(usize, usize)> = Vec::new();
    let mut start: usize = 0;
    while start < characters.len() {
        let found: Option<usize> = boundary(start)
            .then(|| {
                TYPE_WORDS.iter().find_map(|candidate| {
                    let end: usize = start + candidate.len();
                    let matches: bool = characters.get(start..end).is_some_and(|slice| {
                        slice
                            .iter()
                            .zip(candidate.chars())
                            .all(|(character, letter)| ignorecase_equal(*character, letter))
                    });
                    (matches && boundary(end)).then_some(end)
                })
            })
            .flatten();
        match found {
            Some(end) => {
                spans.push((start, end));
                start = end;
            }
            None => start += 1,
        }
    }
    spans
}

/// Python's `re.findall(_TYPE_WORDS, message, re.IGNORECASE)` upper-cased.
pub(crate) fn type_words(message: &str) -> Result<Vec<String>, SemanticFailure> {
    let characters: Vec<char> = message.chars().collect();
    Ok(type_word_spans(&characters)
        .into_iter()
        .map(|(start, end)| upper(&characters[start..end].iter().collect::<String>()))
        .collect())
}

/// Python's `missing_column`: the unknown column and its table, if the message names one.
pub(crate) fn missing_column(
    message: &str,
) -> Result<Option<(String, Option<String>)>, SemanticFailure> {
    let missing: &Regex = pattern(&MISSING)?;
    let Some(captures) = missing.captures(message) else {
        return Ok(None);
    };
    let table: Option<String> = captures.get(2).map(|table| table.as_str().to_owned());
    Ok(Some((captures[1].to_owned(), table)))
}

/// Python's `comparison_help`: a concrete literal for a proven temporal comparison mismatch.
pub(crate) fn comparison_help(types: &[String], dialect: Option<&str>) -> String {
    if types.iter().any(|value| value.contains(TIMESTAMP_TYPE)) {
        let literal = if dialect == Some(BIGQUERY_DIALECT) {
            "TIMESTAMP '2026-04-01 00:00:00+00'"
        } else {
            "TIMESTAMP '2026-04-01'"
        };
        return format!("compare with a timestamp, for example {literal}");
    }
    if types.iter().any(|value| value == DATE_TYPE) {
        return "compare with a date, for example DATE '2026-04-01'".to_owned();
    }
    semantic_help(COMPARISON_CODE)
        .unwrap_or_default()
        .to_owned()
}
