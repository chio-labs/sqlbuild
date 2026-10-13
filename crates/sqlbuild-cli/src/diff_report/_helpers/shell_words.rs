//! Python's `shlex.quote`.

fn is_safe(character: char) -> bool {
    character.is_ascii_alphanumeric() || "_@%+=:,./-".contains(character)
}

/// One shell word, quoted only when it holds characters outside the safe set.
pub(crate) fn quote(word: &str) -> String {
    if word.is_empty() {
        return "''".to_owned();
    }
    if word.chars().all(is_safe) {
        return word.to_owned();
    }
    format!("'{}'", word.replace('\'', "'\"'\"'"))
}
