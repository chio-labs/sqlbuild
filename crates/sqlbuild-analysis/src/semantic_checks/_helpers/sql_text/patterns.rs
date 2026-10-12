//! Regex templates with short tokens for the character classes the semantic checks use.

use regex::Regex;

/// `(template token, class)`: word, ASCII digit, whitespace and ASCII identifier start.
const CLASSES: [(&str, &str); 4] = [
    ("{W}", r"\w"),
    ("{D}", "[0-9]"),
    ("{S}", r"\s"),
    ("{L}", "[A-Za-z_]"),
];

/// An ASCII word matched case-insensitively.
pub(crate) fn ignorecase_word(word: &str) -> String {
    format!("(?i:{word})")
}

/// Compile a pattern template, replacing `{W}`, `{D}`, `{S}` and `{L}` with their classes.
pub(crate) fn compile_pattern(template: &str) -> Result<Regex, String> {
    let pattern: String = CLASSES
        .iter()
        .fold(template.to_owned(), |pattern, (token, class)| {
            pattern.replace(token, class)
        });
    Regex::new(&pattern).map_err(|error| error.to_string())
}
