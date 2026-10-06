//! JSON string escaping of `json.dumps` and orjson.

use crate::json::constants::FIRST_PRINTABLE_ASCII;

/// How a serializer escapes characters outside printable ASCII.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum StringEscaping {
    /// `ensure_ascii=True`: `\uXXXX`, with UTF-16 surrogate pairs above U+FFFF.
    Ascii,
    /// `ensure_ascii=False` and orjson: only control characters are escaped.
    Unicode,
}

fn unicode_escape(unit: u32) -> String {
    format!("\\u{unit:04x}")
}

fn escaped(character: char, escaping: StringEscaping) -> String {
    match character {
        '"' => "\\\"".to_owned(),
        '\\' => "\\\\".to_owned(),
        '\n' => "\\n".to_owned(),
        '\r' => "\\r".to_owned(),
        '\t' => "\\t".to_owned(),
        '\u{8}' => "\\b".to_owned(),
        '\u{c}' => "\\f".to_owned(),
        ' '..='~' => character.to_string(),
        _ if character < FIRST_PRINTABLE_ASCII => unicode_escape(u32::from(character)),
        _ if escaping == StringEscaping::Unicode => character.to_string(),
        _ => character
            .encode_utf16(&mut [0_u16; 2])
            .iter()
            .map(|unit| unicode_escape(u32::from(*unit)))
            .collect(),
    }
}

/// `text` as a quoted JSON string.
pub(crate) fn json_string(text: &str, escaping: StringEscaping) -> String {
    let mut output = String::with_capacity(text.len() + 2);
    output.push('"');
    for character in text.chars() {
        match character {
            ' '..='~' if character != '"' && character != '\\' => output.push(character),
            _ => output.push_str(&escaped(character, escaping)),
        }
    }
    output.push('"');
    output
}
