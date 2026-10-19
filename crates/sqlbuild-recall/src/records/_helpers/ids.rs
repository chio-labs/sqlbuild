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

fn framed(hasher: Sha256, tag: &[u8; 1], bytes: &[u8]) -> Sha256 {
    hasher
        .chain_update(tag)
        .chain_update((bytes.len() as u64).to_le_bytes())
        .chain_update(bytes)
}

fn valued(hasher: Sha256, value: &RecallValue) -> Sha256 {
    match value {
        RecallValue::Null => hasher.chain_update(b"0"),
        RecallValue::Integer(number) => {
            hasher.chain_update(b"i").chain_update(number.to_le_bytes())
        }
        RecallValue::Real(number) => hasher
            .chain_update(b"r")
            .chain_update(number.to_bits().to_le_bytes()),
        RecallValue::Text(text) => framed(hasher, b"t", text.as_bytes()),
        RecallValue::Blob(data) => framed(hasher, b"b", data),
    }
}

/// Hex SHA-256 over every non-NULL named value except `ingested_at` and `content_sha256`, by column name; a NULL column hashes like an absent one.
pub(crate) fn content_sha256(values: &[(&str, RecallValue)]) -> String {
    let mut sorted: Vec<&(&str, RecallValue)> = values
        .iter()
        .filter(|(name, value)| {
            !UNHASHED_COLUMNS.contains(name) && !matches!(value, RecallValue::Null)
        })
        .collect();
    sorted.sort_by(|left, right| left.0.cmp(right.0));
    sorted
        .into_iter()
        .fold(Sha256::new(), |hasher, (name, value)| {
            valued(framed(hasher, b"n", name.as_bytes()), value)
        })
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
