//! Python's `urllib.parse.quote` and `urlencode` over string pairs.

use crate::ingestr_command::constants::URL_ALWAYS_SAFE;

fn quote_with(text: &str, safe: &[u8]) -> String {
    let mut quoted: String = String::with_capacity(text.len());
    for byte in text.bytes() {
        if byte.is_ascii_alphanumeric() || URL_ALWAYS_SAFE.contains(&byte) || safe.contains(&byte) {
            quoted.push(char::from(byte));
        } else {
            quoted.push_str(&format!("%{byte:02X}"));
        }
    }
    quoted
}

/// Python's `urllib.parse.quote(text)`, which keeps `/`.
pub(crate) fn quote(text: &str) -> String {
    quote_with(text, b"/")
}

fn quote_plus(text: &str) -> String {
    quote_with(text, b" ").replace(' ', "+")
}

/// Python's `urlencode` of ordered string pairs.
pub(crate) fn urlencode(pairs: &[(&str, &str)]) -> String {
    pairs
        .iter()
        .map(|(key, value)| format!("{}={}", quote_plus(key), quote_plus(value)))
        .collect::<Vec<String>>()
        .join("&")
}

/// `?` and the encoded pairs, or nothing when there are none.
pub(crate) fn query_suffix(pairs: &[(&str, &str)]) -> String {
    if pairs.is_empty() {
        String::new()
    } else {
        format!("?{}", urlencode(pairs))
    }
}
