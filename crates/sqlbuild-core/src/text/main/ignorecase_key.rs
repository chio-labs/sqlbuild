//! The key two characters share when matched case-insensitively.

/// `character` lowercased, when that is a single character.
pub fn ignorecase_key(character: char) -> char {
    if character.is_ascii() {
        return character.to_ascii_lowercase();
    }
    let mut lower = character.to_lowercase();
    match (lower.next(), lower.next()) {
        (Some(single), None) => single,
        _ => character,
    }
}
