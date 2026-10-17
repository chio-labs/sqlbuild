/// One artifact batch written over a target where some files already exist.
pub(crate) struct WriteBatchTestCase {
    pub(crate) description: &'static str,
    pub(crate) file_count: usize,
    pub(crate) check_existing: bool,
    pub(crate) existing_identical: &'static [usize],
    pub(crate) existing_different: &'static [usize],
    pub(crate) expected_written: usize,
    pub(crate) expected_unchanged: usize,
}

/// One batch with existing non-UTF-8 files at several positions.
pub(crate) struct FirstFailureTestCase {
    pub(crate) description: &'static str,
    pub(crate) file_count: usize,
    pub(crate) failing: &'static [usize],
    pub(crate) expected_failing: usize,
}

/// One batch that queues the same path more than once.
pub(crate) struct RepeatedPathTestCase {
    pub(crate) description: &'static str,
    pub(crate) file_count: usize,
    pub(crate) repeated: usize,
    pub(crate) expected_contents: &'static [u8],
}
