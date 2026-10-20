//! Header values as short digests: an unambiguous byte encoding, hashed and truncated.

use sqlbuild_cache::digest::main::bytes_digest::bytes_digest;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

use crate::header_changes::constants::{HEX, KEPT_DIGEST_BYTES};

/// An unambiguous encoding of header values: a tag byte, then length-prefixed parts.
#[derive(Default)]
pub(crate) struct ValueEncoding {
    bytes: Vec<u8>,
}

impl ValueEncoding {
    fn text(&mut self, tag: u8, text: &str) {
        self.bytes.push(tag);
        self.bytes
            .extend_from_slice(&(text.len() as u64).to_le_bytes());
        self.bytes.extend_from_slice(text.as_bytes());
    }

    fn list(&mut self, tag: u8, items: &[AuthoredValue]) {
        self.bytes.push(tag);
        self.bytes
            .extend_from_slice(&(items.len() as u64).to_le_bytes());
        for item in items {
            self.value(item);
        }
    }

    fn pairs(&mut self, tag: u8, items: &[(String, AuthoredValue)]) {
        self.bytes.push(tag);
        self.bytes
            .extend_from_slice(&(items.len() as u64).to_le_bytes());
        for (key, item) in items {
            self.text(b'k', key);
            self.value(item);
        }
    }

    pub(crate) fn value(&mut self, value: &AuthoredValue) {
        match value {
            AuthoredValue::Null => self.bytes.push(b'n'),
            AuthoredValue::Boolean(flag) => self.bytes.extend_from_slice(&[b'b', u8::from(*flag)]),
            AuthoredValue::BareWord(word) => self.text(b'w', word),
            AuthoredValue::String(string) => self.text(b's', string),
            AuthoredValue::List(items) => self.list(b'l', items),
            AuthoredValue::Map(items) => self.pairs(b'm', items),
            AuthoredValue::Set(items) => self.list(b'e', items),
            AuthoredValue::Tuple(items) => self.list(b't', items),
            AuthoredValue::TypedConstant(items) => self.pairs(b'c', items),
            AuthoredValue::InlineSqlHook(sql) => self.text(b'i', sql),
            AuthoredValue::NamedSqlHook(name, items) => {
                self.text(b'h', name);
                self.pairs(b'a', items);
            }
            AuthoredValue::PythonHook(name, items) => {
                self.text(b'p', name);
                self.pairs(b'a', items);
            }
        }
    }
}

pub(crate) fn short_hex(digest: &[u8]) -> String {
    let mut hex: String = String::with_capacity(KEPT_DIGEST_BYTES * 2);
    for byte in &digest[..KEPT_DIGEST_BYTES] {
        hex.push(char::from(HEX[usize::from(byte >> 4)]));
        hex.push(char::from(HEX[usize::from(byte & 0x0f)]));
    }
    hex
}

/// The short digest of one header value.
pub(crate) fn value_digest(value: &AuthoredValue) -> String {
    let mut encoding: ValueEncoding = ValueEncoding::default();
    encoding.value(value);
    short_hex(&bytes_digest(&encoding.bytes))
}
