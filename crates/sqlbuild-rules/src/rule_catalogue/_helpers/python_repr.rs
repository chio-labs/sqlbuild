//! Python `repr` text of the strings and dictionaries guidance prints.

use crate::rule_catalogue::constants::{DELETE_CHARACTER, FIRST_PRINTABLE};

/// `repr(text)` for a Python `str`.
pub(crate) fn string_repr(text: &str) -> String {
    let quote: char = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut rendered: String = String::with_capacity(text.len() + 2);
    rendered.push(quote);
    for character in text.chars() {
        match character {
            '\\' => rendered.push_str("\\\\"),
            '\n' => rendered.push_str("\\n"),
            '\r' => rendered.push_str("\\r"),
            '\t' => rendered.push_str("\\t"),
            _ if character == quote => {
                rendered.push('\\');
                rendered.push(character);
            }
            _ if (character as u32) < FIRST_PRINTABLE || character as u32 == DELETE_CHARACTER => {
                rendered.push_str(&format!("\\x{:02x}", character as u32));
            }
            _ => rendered.push(character),
        }
    }
    rendered.push(quote);
    rendered
}

/// `repr(dict)` of string keys and already-rendered value texts, in the given order.
pub(crate) fn dict_repr<'a>(entries: impl IntoIterator<Item = (&'a str, String)>) -> String {
    let parts: Vec<String> = entries
        .into_iter()
        .map(|(key, value)| format!("{}: {value}", string_repr(key)))
        .collect();
    format!("{{{}}}", parts.join(", "))
}
