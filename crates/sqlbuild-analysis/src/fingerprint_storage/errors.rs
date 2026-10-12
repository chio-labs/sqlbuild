//! Failures of encoding and decoding fingerprint rows.

use std::fmt::{self, Display};

/// Invalid insert input, with Python's `FingerprintInputError` message.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FingerprintStorageError {
    EmptyInsert,
    NonPositiveBatchSize,
    NonPositiveBatchBytes,
}

impl Display for FingerprintStorageError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::EmptyInsert => "fingerprint insert requires at least one row",
            Self::NonPositiveBatchSize => "fingerprint batch size must be positive",
            Self::NonPositiveBatchBytes => "fingerprint batch byte limit must be positive",
        })
    }
}

impl std::error::Error for FingerprintStorageError {}

/// Why stored base64 text is not base64-encoded UTF-8, as Python's decoders report it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum StorageDecodeError {
    /// `binascii.Error` from strict base64 decoding.
    Base64(String),
    /// `UnicodeDecodeError` from UTF-8 decoding the base64 payload.
    Utf8 {
        bytes: Vec<u8>,
        start: usize,
        end: usize,
        reason: &'static str,
    },
}
