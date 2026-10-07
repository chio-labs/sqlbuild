use std::path::Path;

use crate::store::errors::StoreDecodeError;
use crate::store::models::NativeStore;

/// A change applied to a saved store file before it is opened again.
pub(crate) type StoreFileEdit = fn(&Path);

pub(crate) struct NativeStoreOpenTestCase {
    pub(crate) description: &'static str,
    pub(crate) kind: &'static str,
    pub(crate) environment: &'static str,
    pub(crate) edit: StoreFileEdit,
    pub(crate) expected_value: Option<&'static [u8]>,
    pub(crate) expected_metadata: &'static [u8],
}

pub(crate) struct NativeStoreRetentionTestCase {
    pub(crate) description: &'static str,
    pub(crate) unused_saves: u64,
    pub(crate) expected_retained: bool,
}

pub(crate) struct NativeStoreDiscardTestCase {
    pub(crate) description: &'static str,
    pub(crate) prepare: fn(&mut NativeStore),
    pub(crate) expected_old_entry: bool,
}

pub(crate) struct RecordReaderTestCase {
    pub(crate) description: &'static str,
    pub(crate) bytes: fn() -> Vec<u8>,
    pub(crate) expected_record: Result<(String, u64), StoreDecodeError>,
}
