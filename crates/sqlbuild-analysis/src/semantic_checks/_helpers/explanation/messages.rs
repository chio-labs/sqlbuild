//! Python's semantic message rewriting and code-owned help texts.

use std::sync::LazyLock;

use regex::{Captures, Regex};

use crate::semantic_checks::_helpers::sql_text::text::ascii;
use crate::semantic_checks::constants::{
    BIGQUERY_DIALECT, COMPARISON_CODE, CONTEXT_SUFFIX_PATTERN, DATE_TYPE, MISSING_PATTERN,
    QUOTED_PIECE_PATTERN, SEMANTIC_HELP, TIMESTAMP_TYPE, TYPE_WORDS_PATTERN,
};
use crate::semantic_checks::models::SemanticDeferral;

static TYPE_WORDS: LazyLock<Result<Regex, String>> = LazyLock::new(|| compiled(TYPE_WORDS_PATTERN));
static MISSING: LazyLock<Result<Regex, String>> = LazyLock::new(|| compiled(MISSING_PATTERN));
static CONTEXT_SUFFIX: LazyLock<Result<Regex, String>> =
    LazyLock::new(|| compiled(CONTEXT_SUFFIX_PATTERN));
static QUOTED_PIECE: LazyLock<Result<Regex, String>> =
    LazyLock::new(|| compiled(QUOTED_PIECE_PATTERN));

/// Compile one of this lane's constant patterns.
pub(crate) fn compiled(pattern: &str) -> Result<Regex, String> {
    Regex::new(pattern).map_err(|error| error.to_string())
}

/// A compiled constant pattern, or a native-failure deferral if it did not compile.
pub(crate) fn pattern(
    compiled: &'static Result<Regex, String>,
) -> Result<&'static Regex, SemanticDeferral> {
    compiled
        .as_ref()
        .map_err(|_| SemanticDeferral::NativeFailure)
}

/// A message Python's regexes read the same way, or a deferral.
fn message_text(message: &str) -> Result<&str, SemanticDeferral> {
    if message.contains('\n') {
        return Err(SemanticDeferral::NonAsciiText);
    }
    ascii(message)
}

/// Python's `semantic_help`.
pub(crate) fn semantic_help(code: &str) -> Option<&'static str> {
    SEMANTIC_HELP
        .iter()
        .find(|(known, _)| *known == code)
        .map(|(_, help)| *help)
}

/// Python's `sentence_message`: drop the context suffix and upper-case unquoted type words.
pub(crate) fn sentence_message(message: &str) -> Result<String, SemanticDeferral> {
    let suffix: &Regex = pattern(&CONTEXT_SUFFIX)?;
    let quoted: &Regex = pattern(&QUOTED_PIECE)?;
    let words: &Regex = pattern(&TYPE_WORDS)?;
    let text = suffix.replace(message_text(message)?, "");
    let mut sentence = String::with_capacity(text.len());
    let mut last: usize = 0;
    for piece in quoted.find_iter(&text) {
        sentence.push_str(&upper_type_words(words, &text[last..piece.start()]));
        sentence.push_str(piece.as_str());
        last = piece.end();
    }
    sentence.push_str(&upper_type_words(words, &text[last..]));
    Ok(sentence)
}

fn upper_type_words(words: &Regex, text: &str) -> String {
    words.replace_all(text, upper_match).into_owned()
}

fn upper_match(captures: &Captures<'_>) -> String {
    captures[0].to_ascii_uppercase()
}

/// Python's `re.findall(_TYPE_WORDS, message, re.IGNORECASE)` upper-cased.
pub(crate) fn type_words(message: &str) -> Result<Vec<String>, SemanticDeferral> {
    let words: &Regex = pattern(&TYPE_WORDS)?;
    let mut found: Vec<String> = Vec::new();
    for captures in words.captures_iter(message_text(message)?) {
        found.push(captures[1].to_ascii_uppercase());
    }
    Ok(found)
}

/// Python's `missing_column`: the unknown column and its table, if the message names one.
pub(crate) fn missing_column(
    message: &str,
) -> Result<Option<(String, Option<String>)>, SemanticDeferral> {
    let missing: &Regex = pattern(&MISSING)?;
    let Some(captures) = missing.captures(message_text(message)?) else {
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
