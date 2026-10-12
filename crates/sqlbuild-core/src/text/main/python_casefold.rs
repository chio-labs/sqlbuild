//! Python's `str.casefold`.

use crate::text::_helpers::python_tables::PYTHON_CASEFOLD;

/// Python's `text.casefold()`.
#[must_use]
pub fn python_casefold(text: &str) -> String {
    let mut folded: String = String::with_capacity(text.len());
    for character in text.chars() {
        let code: u32 = u32::from(character);
        match PYTHON_CASEFOLD.binary_search_by_key(&code, |(entry, _)| *entry) {
            Ok(index) => folded.push_str(PYTHON_CASEFOLD[index].1),
            Err(_) => folded.extend(character.to_lowercase()),
        }
    }
    folded
}
