//! Deterministic record IDs and content digests.

use sha2::{Digest, Sha256};

use crate::records::constants::{DIAGNOSTIC_RECORD_ID_INFIX, OUTPUT_RECORD_ID_INFIX};
use crate::records::models::RecallValue;
use crate::schema::constants::UNHASHED_COLUMNS;

/// `<invocation_id>:command-output:<sequence>`, the command-output sink record ID scheme.
pub(crate) fn output_record_id(invocation_id: &str, sequence: u64) -> String {
    format!("{invocation_id}:{OUTPUT_RECORD_ID_INFIX}:{sequence}")
}

/// `<invocation_id>:diagnostic:<sequence>`.
pub(crate) fn diagnostic_record_id(invocation_id: &str, sequence: u64) -> String {
    format!("{invocation_id}:{DIAGNOSTIC_RECORD_ID_INFIX}:{sequence}")
}

fn framed(tag: &[u8; 1], bytes: &[u8]) -> Vec<u8> {
    let mut frame: Vec<u8> = Vec::with_capacity(bytes.len() + 9);
    frame.extend_from_slice(tag);
    frame.extend_from_slice(&(bytes.len() as u64).to_le_bytes());
    frame.extend_from_slice(bytes);
    frame
}

fn encoded(value: &RecallValue) -> Vec<u8> {
    match value {
        RecallValue::Null => b"0".to_vec(),
        RecallValue::Integer(number) => [b"i".as_slice(), &number.to_le_bytes()].concat(),
        RecallValue::Real(number) => [b"r".as_slice(), &number.to_bits().to_le_bytes()].concat(),
        RecallValue::Text(text) => framed(b"t", text.as_bytes()),
        RecallValue::Blob(data) => framed(b"b", data),
    }
}

/// Hex SHA-256 over every named value except `ingested_at` and `content_sha256`, by column name.
pub(crate) fn content_sha256(values: &[(&str, RecallValue)]) -> String {
    let mut sorted: Vec<&(&str, RecallValue)> = values
        .iter()
        .filter(|(name, _)| !UNHASHED_COLUMNS.contains(name))
        .collect();
    sorted.sort_by(|left, right| left.0.cmp(right.0));
    let mut hasher = Sha256::new();
    for (name, value) in sorted {
        hasher.update(framed(b"n", name.as_bytes()));
        hasher.update(encoded(value));
    }
    hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
