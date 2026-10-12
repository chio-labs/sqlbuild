//! Python's `repr` of a `str`.

/// Python's `repr` of a string; non-ASCII characters print unless they are control or separator characters.
#[must_use]
pub fn python_str_repr(value: &str) -> String {
    let quote: char = if value.contains('\'') && !value.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut text: String = String::with_capacity(value.len() + 2);
    text.push(quote);
    for character in value.chars() {
        let code: u32 = u32::from(character);
        match character {
            '\\' => text.push_str("\\\\"),
            '\t' => text.push_str("\\t"),
            '\n' => text.push_str("\\n"),
            '\r' => text.push_str("\\r"),
            _ if character == quote => {
                text.push('\\');
                text.push(character);
            }
            '\0'..='\x1f' | '\x7f' => text.push_str(&format!("\\x{code:02x}")),
            _ if character.is_ascii() || is_printable(character) => text.push(character),
            '\u{80}'..='\u{ff}' => text.push_str(&format!("\\x{code:02x}")),
            '\u{100}'..='\u{ffff}' => text.push_str(&format!("\\u{code:04x}")),
            _ => text.push_str(&format!("\\U{code:08x}")),
        }
    }
    text.push(quote);
    text
}

fn is_printable(character: char) -> bool {
    !character.is_control() && !character.is_whitespace()
}
