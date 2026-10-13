//! UTF-8 decoding failures described as CPython's decoder reports them.

use crate::fingerprint_storage::errors::StorageDecodeError;

/// `bytes` as text, or Python's `UnicodeDecodeError` range and reason.
pub(crate) fn decode_utf8(bytes: Vec<u8>) -> Result<String, StorageDecodeError> {
    let error = match String::from_utf8(bytes) {
        Ok(text) => return Ok(text),
        Err(error) => error,
    };
    let utf8_error = error.utf8_error();
    let bytes: Vec<u8> = error.into_bytes();
    let start: usize = utf8_error.valid_up_to();
    let (end, reason): (usize, &'static str) = match utf8_error.error_len() {
        None => (bytes.len(), "unexpected end of data"),
        Some(length) if length == 1 && invalid_start_byte(bytes[start]) => {
            (start + 1, "invalid start byte")
        }
        Some(length) => (start + length, "invalid continuation byte"),
    };
    Err(StorageDecodeError::Utf8 {
        bytes,
        start,
        end,
        reason,
    })
}

fn invalid_start_byte(byte: u8) -> bool {
    matches!(byte, 0x80..=0xC1 | 0xF5..=0xFF)
}
