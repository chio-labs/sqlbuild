//! JSON string escaping of `json.dumps` and orjson.

use std::fmt::Write;

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

fn with_unicode_escape(mut output: String, unit: u32) -> String {
    let _ = write!(output, "\\u{unit:04x}");
    output
}

fn with_escaped(mut output: String, character: char, escaping: StringEscaping) -> String {
    match character {
        '"' => output.push_str("\\\""),
        '\\' => output.push_str("\\\\"),
        '\n' => output.push_str("\\n"),
        '\r' => output.push_str("\\r"),
        '\t' => output.push_str("\\t"),
        '\u{8}' => output.push_str("\\b"),
        '\u{c}' => output.push_str("\\f"),
        ' '..='~' => output.push(character),
        _ if character < FIRST_PRINTABLE_ASCII => {
            return with_unicode_escape(output, u32::from(character));
        }
        _ if escaping == StringEscaping::Unicode => output.push(character),
        _ => {
            for unit in character.encode_utf16(&mut [0_u16; 2]).iter() {
                output = with_unicode_escape(output, u32::from(*unit));
            }
        }
    }
    output
}

/// Whether `byte` is printable ASCII that a JSON string carries unescaped.
fn plain(byte: u8) -> bool {
    (b' '..=b'~').contains(&byte) && byte != b'"' && byte != b'\\'
}

/// `output` followed by `text` as a quoted JSON string.
pub(crate) fn with_json_string(mut output: String, text: &str, escaping: StringEscaping) -> String {
    output.reserve(text.len() + 2);
    output.push('"');
    let mut rest: &str = text;
    while !rest.is_empty() {
        let run: usize = rest
            .bytes()
            .position(|byte| !plain(byte))
            .unwrap_or(rest.len());
        output.push_str(&rest[..run]);
        rest = &rest[run..];
        let Some(character) = rest.chars().next() else {
            break;
        };
        output = with_escaped(output, character, escaping);
        rest = &rest[character.len_utf8()..];
    }
    output.push('"');
    output
}

/// `output` followed by UTF-16 `units` as a quoted JSON string; `ensure_ascii` escapes lone surrogates.
pub(crate) fn with_json_utf16_string(
    mut output: String,
    units: &[u16],
    escaping: StringEscaping,
) -> Result<String, JsonEmitError> {
    output.reserve(units.len() + 2);
    output.push('"');
    for decoded in char::decode_utf16(units.iter().copied()) {
        output = match (decoded, escaping) {
            (Ok(character), _) => with_escaped(output, character, escaping),
            (Err(lone), StringEscaping::Ascii) => {
                with_unicode_escape(output, u32::from(lone.unpaired_surrogate()))
            }
            (Err(_), StringEscaping::Unicode) => return Err(JsonEmitError::LoneSurrogate),
        };
    }
    output.push('"');
    Ok(output)
}
