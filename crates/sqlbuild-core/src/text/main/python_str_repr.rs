//! Python's `repr` of a `str`.

/// Python's `repr` of a string, or `None` when it holds text whose escaping needs Unicode tables.
pub fn python_str_repr(value: &str) -> Option<String> {
    if !value.is_ascii() {
        return None;
    }
    let quote: char = if value.contains('\'') && !value.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut text: String = String::with_capacity(value.len() + 2);
    text.push(quote);
    for character in value.chars() {
        match character {
            '\\' => text.push_str("\\\\"),
            '\t' => text.push_str("\\t"),
            '\n' => text.push_str("\\n"),
            '\r' => text.push_str("\\r"),
            _ if character == quote => {
                text.push('\\');
                text.push(character);
            }
            _ if character < ' ' || character == '\x7f' => {
                text.push_str(&format!("\\x{:02x}", u32::from(character)));
            }
            _ => text.push(character),
        }
    }
    text.push(quote);
    Some(text)
}
