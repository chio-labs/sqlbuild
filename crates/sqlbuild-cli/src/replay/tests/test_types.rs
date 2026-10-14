/// Elapsed milliseconds and Python's `f"{ms / 1000:.1f}"`.
pub(crate) struct TenthsTestCase {
    pub(crate) description: &'static str,
    pub(crate) milliseconds: i64,
    pub(crate) expected_text: &'static str,
}

/// Existing records in a launch record directory and which survive one more write.
pub(crate) struct LaunchRecordWriteTestCase {
    pub(crate) description: &'static str,
    pub(crate) existing_records: usize,
    pub(crate) expected_names: Vec<String>,
}
