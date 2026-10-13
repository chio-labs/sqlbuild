use crate::fingerprint_storage::errors::{FingerprintStorageError, StorageDecodeError};
use crate::fingerprint_storage::models::LatestIndex;

pub(crate) struct DecodeTestCase {
    pub(crate) description: &'static str,
    pub(crate) storage: &'static str,
    pub(crate) expected_decoded: Result<&'static str, StorageDecodeError>,
}

pub(crate) struct BatchTestCase {
    pub(crate) description: &'static str,
    pub(crate) definition_lengths: &'static [usize],
    pub(crate) batch_size: i64,
    pub(crate) batch_max_bytes: i64,
    pub(crate) expected_lengths: Result<&'static [usize], FingerprintStorageError>,
}

pub(crate) struct InsertTestCase {
    pub(crate) description: &'static str,
    pub(crate) definitions: &'static [&'static str],
    pub(crate) expected_sql: Result<&'static str, FingerprintStorageError>,
}

pub(crate) struct LatestIndexTestCase {
    pub(crate) description: &'static str,
    pub(crate) identities: &'static [(&'static str, &'static str)],
    pub(crate) expected_index: LatestIndex,
}
