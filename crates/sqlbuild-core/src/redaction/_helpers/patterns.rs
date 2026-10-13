//! The four secret patterns, compiled once per process.

use std::sync::LazyLock;

use regex::{Regex, RegexBuilder};

use crate::redaction::constants::{
    AUTHORIZATION_PATTERN, BEARER_PATTERN, PATTERN_SIZE_LIMIT, SECRET_VALUE_PATTERN,
    URI_CREDENTIAL_PATTERN,
};

pub(crate) static AUTHORIZATION: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| compiled(AUTHORIZATION_PATTERN));
pub(crate) static BEARER: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| compiled(BEARER_PATTERN));
pub(crate) static SECRET_VALUE: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| compiled(SECRET_VALUE_PATTERN));
pub(crate) static URI_CREDENTIAL: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| compiled(URI_CREDENTIAL_PATTERN));

fn compiled(pattern: &str) -> Result<Regex, regex::Error> {
    RegexBuilder::new(pattern)
        .size_limit(PATTERN_SIZE_LIMIT)
        .build()
}

/// `pattern.sub(replacement, text)`; a pattern that failed to compile matches nothing.
pub(crate) fn substituted(
    pattern: &LazyLock<Result<Regex, regex::Error>>,
    text: &str,
    replacement: &str,
) -> String {
    match pattern.as_ref() {
        Ok(regex) => regex.replace_all(text, replacement).into_owned(),
        Err(_) => text.to_owned(),
    }
}
