//! Python's `shlex.quote`.

/// Python's `shlex.quote(text)`: safe ASCII text unchanged, anything else single-quoted.
#[must_use]
pub fn shell_quote(text: &str) -> String {
    if text.is_empty() {
        return "''".to_owned();
    }
    let safe: bool = text
        .chars()
        .all(|character| character.is_ascii_alphanumeric() || "_@%+=:,./-".contains(character));
    if safe {
        return text.to_owned();
    }
    format!("'{}'", text.replace('\'', "'\"'\"'"))
}
