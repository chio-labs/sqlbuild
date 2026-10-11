/// One UTC instant and the text Python's `isoformat()` gives it.
pub(crate) struct TimestampTestCase {
    pub(crate) description: &'static str,
    pub(crate) microseconds: i64,
    pub(crate) expected_timestamp: &'static str,
}

/// One capture's metadata and the exact `metadata_to_json` text.
pub(crate) struct MetadataTestCase {
    pub(crate) description: &'static str,
    pub(crate) target: Option<&'static str>,
    /// `(completed_at seconds, exit code, stdout bytes, stderr bytes)` once complete.
    pub(crate) end: Option<(i64, i64, usize, usize)>,
    pub(crate) expected_json: &'static str,
}

/// Completed captures already in the log root and how many pruning keeps.
pub(crate) struct PruneTestCase {
    pub(crate) description: &'static str,
    pub(crate) existing: usize,
    pub(crate) expected_complete: usize,
}
