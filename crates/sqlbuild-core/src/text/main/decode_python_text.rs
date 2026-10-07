//! Decode authored file bytes the way Python's `Path.read_text(encoding="utf-8")` does.

use crate::text::errors::TextDecodeError;

/// Decode strict UTF-8 with universal newlines (`\r\n` and `\r` become `\n`), keeping a BOM.
pub fn decode_python_text(bytes: &[u8]) -> Result<String, TextDecodeError> {
    let text = std::str::from_utf8(bytes).map_err(|error| TextDecodeError {
        valid_up_to: error.valid_up_to(),
        error_len: error.error_len(),
    })?;
    if !bytes.contains(&b'\r') {
        return Ok(text.to_owned());
    }
    Ok(text.replace("\r\n", "\n").replace('\r', "\n"))
}
