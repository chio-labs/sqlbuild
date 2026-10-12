//! Bounded fingerprint insert batches.

use crate::fingerprint_storage::errors::FingerprintStorageError;
use crate::fingerprint_storage::main::insert_sql::insert_sql;
use crate::fingerprint_storage::models::StoredFingerprint;

/// Batch lengths in order, each within `batch_size` rows and `batch_max_bytes` of row SQL.
pub fn insert_batch_lengths(
    qualified_name: &str,
    fingerprints: &[StoredFingerprint],
    batch_size: i64,
    batch_max_bytes: i64,
) -> Result<Vec<usize>, FingerprintStorageError> {
    if batch_size < 1 {
        return Err(FingerprintStorageError::NonPositiveBatchSize);
    }
    if batch_max_bytes < 1 {
        return Err(FingerprintStorageError::NonPositiveBatchBytes);
    }
    let mut lengths: Vec<usize> = Vec::new();
    let mut current_length: usize = 0;
    let mut current_bytes: i64 = 0;
    for fingerprint in fingerprints {
        let single_row_bytes: i64 =
            i64::try_from(insert_sql(qualified_name, std::slice::from_ref(fingerprint))?.len())
                .unwrap_or(i64::MAX);
        if current_length > 0
            && (i64::try_from(current_length).unwrap_or(i64::MAX) >= batch_size
                || current_bytes.saturating_add(single_row_bytes) > batch_max_bytes)
        {
            lengths.push(current_length);
            current_length = 0;
            current_bytes = 0;
        }
        current_length += 1;
        current_bytes = current_bytes.saturating_add(single_row_bytes);
    }
    if current_length > 0 {
        lengths.push(current_length);
    }
    Ok(lengths)
}
