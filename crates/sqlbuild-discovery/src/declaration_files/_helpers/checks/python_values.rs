//! The Python type of a projected header value, as the discovery parsers' `isinstance` checks see it.

use crate::declaration_files::_helpers::checks::stops::ParseStop;
use crate::models::{DiscoveryFailure, FailureKind};
use sqlbuild_core::text::main::is_python_decimal::is_python_decimal;
use sqlbuild_core::text::main::python_strip::python_strip;
use sqlbuild_core::text::models::PythonText;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

/// The Python whose `\d` decides bare-word numbers, and the file a rejected word is reported in.
#[derive(Clone, Copy, Debug)]
pub(crate) struct WordRules<'file> {
    pub(crate) python: PythonText,
    pub(crate) file_path: &'file str,
}

/// The Python type a header value projects to.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum PythonType {
    None,
    Bool,
    Int,
    Float,
    Str,
    List,
    Dict,
    /// `AuthoredSqlSet`, a tuple, a `constant(...)` call or a hook entry.
    Other,
}

/// The projected type; a bare number written with non-ASCII digits is rejected.
pub(crate) fn python_type(
    value: &AuthoredValue,
    words: WordRules,
) -> Result<PythonType, ParseStop> {
    Ok(match value {
        AuthoredValue::Null => PythonType::None,
        AuthoredValue::Boolean(_) => PythonType::Bool,
        AuthoredValue::BareWord(word) => word_type(word, words)?,
        AuthoredValue::String(_) => PythonType::Str,
        AuthoredValue::List(_) => PythonType::List,
        AuthoredValue::Map(_) => PythonType::Dict,
        AuthoredValue::Set(_)
        | AuthoredValue::Tuple(_)
        | AuthoredValue::TypedConstant(_)
        | AuthoredValue::InlineSqlHook(_)
        | AuthoredValue::NamedSqlHook(..)
        | AuthoredValue::PythonHook(..) => PythonType::Other,
    })
}

/// The text of a value that projects to `str`, or `None` for any other type.
pub(crate) fn python_str<'value>(
    value: &'value AuthoredValue,
    words: WordRules,
) -> Result<Option<&'value str>, ParseStop> {
    Ok(match value {
        AuthoredValue::String(text) => Some(text),
        AuthoredValue::BareWord(word) if word_type(word, words)? == PythonType::Str => Some(word),
        _ => None,
    })
}

/// `isinstance(value, str) and value.strip()`.
pub(crate) fn non_empty_str<'value>(
    value: &'value AuthoredValue,
    words: WordRules,
) -> Result<Option<&'value str>, ParseStop> {
    Ok(python_str(value, words)?.filter(|text| !python_strip(text).is_empty()))
}

/// Python's `dict.get(key)`.
pub(crate) fn get<'a>(
    values: &'a [(String, AuthoredValue)],
    key: &str,
) -> Option<&'a AuthoredValue> {
    values
        .iter()
        .find(|(candidate, _)| candidate == key)
        .map(|(_, value)| value)
}

/// The keys outside `allowed`, sorted as Python's `sorted(set(values) - allowed)`.
pub(crate) fn unknown_keys(values: &[(String, AuthoredValue)], allowed: &[&str]) -> Vec<String> {
    let mut unknown: Vec<String> = values
        .iter()
        .map(|(key, _)| key.clone())
        .filter(|key| !allowed.contains(&key.as_str()))
        .collect();
    unknown.sort_unstable();
    unknown.dedup();
    unknown
}

/// `re.fullmatch(r"^[A-Za-z_][A-Za-z0-9_]*$", text)`.
pub(crate) fn is_identifier(text: &str) -> bool {
    let mut characters = text.chars();
    characters
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic() || first == '_')
        && characters.all(|character| character.is_ascii_alphanumeric() || character == '_')
}

/// A failure of `kind` with `message` and no help.
pub(crate) fn failure(kind: FailureKind, message: String) -> ParseStop {
    ParseStop::Failed(DiscoveryFailure::new(kind, message))
}

/// `_parse_word_value`: `true`, `false` and `null` are parsed as values; numbers become numbers.
fn word_type(word: &str, words: WordRules) -> Result<PythonType, ParseStop> {
    if !word.is_ascii() {
        if is_unicode_number(word, words.python) {
            return Err(ParseStop::Failed(DiscoveryFailure {
                kind: FailureKind::Declaration,
                message: format!(
                    "{} has the bare number '{word}', written with non-ASCII digits",
                    words.file_path
                ),
                help: Some(format!(
                    "Quote it to keep it as text (\"{word}\"), or write the number with ASCII \
                     digits 0-9"
                )),
            }));
        }
        return Ok(PythonType::Str);
    }
    Ok(match word {
        "true" | "false" => PythonType::Bool,
        "null" => PythonType::None,
        _ if is_integer(word) => PythonType::Int,
        _ if is_float(word) => PythonType::Float,
        _ => PythonType::Str,
    })
}

fn unsigned(word: &str) -> &str {
    word.strip_prefix(['+', '-']).unwrap_or(word)
}

/// `^[+-]?\d+$` over ASCII text.
fn is_integer(word: &str) -> bool {
    let digits = unsigned(word);
    !digits.is_empty() && digits.bytes().all(|byte| byte.is_ascii_digit())
}

/// `^[+-]?(?:\d+\.\d*|\d*\.\d+)$` over ASCII text.
fn is_float(word: &str) -> bool {
    let Some((whole, fraction)) = unsigned(word).split_once('.') else {
        return false;
    };
    let digits = |part: &str| part.bytes().all(|byte| byte.is_ascii_digit());
    digits(whole) && digits(fraction) && !(whole.is_empty() && fraction.is_empty())
}

/// Whether Python's `^[+-]?\d+$` or float pattern, with Unicode `\d`, matches a non-ASCII word.
fn is_unicode_number(word: &str, python: PythonText) -> bool {
    let digits = |part: &str| {
        part.chars()
            .all(|character| is_python_decimal(python, character))
    };
    let unsigned = unsigned(word);
    if !unsigned.is_empty() && digits(unsigned) {
        return true;
    }
    unsigned.split_once('.').is_some_and(|(whole, fraction)| {
        digits(whole) && digits(fraction) && !(whole.is_empty() && fraction.is_empty())
    })
}
