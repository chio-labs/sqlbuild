//! JSON string escaping of `json.dumps` and orjson.

use crate::json::constants::FIRST_PRINTABLE_ASCII;
use crate::json::errors::JsonEmitError;

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

/// UTF-16 `units` as a quoted JSON string; `ensure_ascii` escapes a lone surrogate as `\uXXXX`.
pub(crate) fn json_utf16_string(
    units: &[u16],
    escaping: StringEscaping,
) -> Result<String, JsonEmitError> {
    let mut output = String::with_capacity(units.len() + 2);
    output.push('"');
    for decoded in char::decode_utf16(units.iter().copied()) {
        match (decoded, escaping) {
            (Ok(character), _) => output.push_str(&escaped_or_plain(character, escaping)),
            (Err(lone), StringEscaping::Ascii) => {
                output.push_str(&unicode_escape(u32::from(lone.unpaired_surrogate())));
            }
            (Err(_), StringEscaping::Unicode) => return Err(JsonEmitError::LoneSurrogate),
        }
    }
    output.push('"');
    Ok(output)
}

fn escaped_or_plain(character: char, escaping: StringEscaping) -> String {
    match character {
        ' '..='~' if character != '"' && character != '\\' => character.to_string(),
        _ => escaped(character, escaping),
    }
}
