use crate::scope_cache::models::CacheMiss;

/// A written envelope, how its bytes are altered, and what reading it back gives.
pub(super) struct ReadBackTestCase {
    pub(super) description: &'static str,
    pub(super) read_fingerprint: &'static str,
    pub(super) altered: fn(Vec<u8>) -> Vec<u8>,
    pub(super) expected_read: Result<(), CacheMiss>,
}

/// A config file name and text, and the bytes the fingerprint hashes for it.
pub(super) struct ConfigBytesTestCase {
    pub(super) description: &'static str,
    pub(super) name: &'static str,
    pub(super) text: &'static str,
    pub(super) expected_bytes: &'static str,
}
