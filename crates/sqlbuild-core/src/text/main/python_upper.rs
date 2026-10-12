//! Upper-casing.

/// `text` upper-cased.
pub fn python_upper(text: &str) -> String {
    if text.is_ascii() {
        return text.to_ascii_uppercase();
    }
    text.to_uppercase()
}
