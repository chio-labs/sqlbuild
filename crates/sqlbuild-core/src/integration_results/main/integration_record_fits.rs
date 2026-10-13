//! The size limit a reader applies before decoding a record.

use crate::integration_results::constants::MAX_RECORD_BYTES;

/// Whether a record of `byte_length` UTF-8 bytes is within the record limit.
#[must_use]
pub fn integration_record_fits(byte_length: usize) -> bool {
    byte_length <= MAX_RECORD_BYTES
}
