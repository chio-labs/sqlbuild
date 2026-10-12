//! Python's `substitute_placeholder_defaults`.

use sqlbuild_core::text::main::is_word_char::is_word_char;

use crate::constants::PLACEHOLDER_PREFIX;

/// `substitute_placeholder_defaults`: `@@@name` becomes its default; unknown names stay.
pub fn placeholder_defaults(sql: &str, placeholders: &[(String, String)]) -> String {
    let mut result: String = String::with_capacity(sql.len());
    let mut rest: &str = sql;
    while let Some(start) = rest.find(PLACEHOLDER_PREFIX) {
        result.push_str(&rest[..start]);
        let after: &str = &rest[start + PLACEHOLDER_PREFIX.len()..];
        let length: usize = after
            .find(|character: char| !is_word(character))
            .unwrap_or(after.len());
        if length == 0 {
            result.push_str(&rest[start..=start]);
            rest = &rest[start + 1..];
            continue;
        }
        let name: &str = &after[..length];
        match placeholders
            .iter()
            .find(|(placeholder, _)| placeholder == name)
        {
            Some((_, default)) => result.push_str(default),
            None => {
                result.push_str(PLACEHOLDER_PREFIX);
                result.push_str(name);
            }
        }
        rest = &after[length..];
    }
    result.push_str(rest);
    result
}

/// A character Python's `\w` matches.
fn is_word(character: char) -> bool {
    is_word_char(character)
}
