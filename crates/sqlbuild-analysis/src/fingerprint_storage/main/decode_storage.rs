//! Stored definition text decoding.

use crate::fingerprint_storage::_helpers::base64::decode_strict;
use crate::fingerprint_storage::_helpers::utf8::decode_utf8;
use crate::fingerprint_storage::errors::StorageDecodeError;

/// Stored ASCII base64 text decoded to UTF-8, failing as Python's strict decoders do.
pub fn decode_storage(storage: &str) -> Result<String, StorageDecodeError> {
    decode_utf8(decode_strict(storage.as_bytes()).map_err(StorageDecodeError::Base64)?)
}
