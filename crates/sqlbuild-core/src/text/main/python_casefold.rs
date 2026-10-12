//! Case-insensitive comparison keys.

/// `text` lowercased, for case-insensitive comparison.
pub fn python_casefold(text: &str) -> String {
    if text.is_ascii() {
        return text.to_ascii_lowercase();
    }
    text.to_lowercase()
}
