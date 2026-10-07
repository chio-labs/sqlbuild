use std::path::{Path, PathBuf};

pub(crate) struct ContentDigestTestCase {
    pub(crate) description: &'static str,
    pub(crate) left: &'static [&'static str],
    pub(crate) right: &'static [&'static str],
    pub(crate) expected_equal: bool,
}

pub(crate) struct HexDigestTestCase {
    pub(crate) description: &'static str,
    pub(crate) parts: &'static [&'static str],
    pub(crate) expected_length: usize,
}

/// An edit applied to a fresh copy of the fingerprint test project.
pub(crate) type ProjectEdit = fn(&Path);

pub(crate) struct FingerprintProjectFilesTestCase {
    pub(crate) description: &'static str,
    pub(crate) edit: ProjectEdit,
    pub(crate) expected_changed: bool,
}

pub(crate) struct FingerprintFailureTestCase {
    pub(crate) description: &'static str,
    pub(crate) root: fn(&Path) -> PathBuf,
    pub(crate) expected_failure: bool,
}

pub(crate) struct DigestFilesTestCase {
    pub(crate) description: &'static str,
    pub(crate) path: fn(&Path) -> PathBuf,
    pub(crate) expected_digest_of: Option<&'static str>,
}
