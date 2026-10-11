use std::path::Path;

/// One stored slot edited before it is read back.
pub(crate) struct EntryReadTestCase {
    pub(crate) description: &'static str,
    pub(crate) edit: fn(&Path),
    pub(crate) expected_read: bool,
}

/// Slots stored oldest first under one retention limit.
pub(crate) struct SlotPruneTestCase {
    pub(crate) description: &'static str,
    pub(crate) slots: u64,
    pub(crate) max_entries: usize,
    pub(crate) expected_kept: &'static [&'static str],
}

/// One report and the compile_timings span expected inside it.
pub(crate) struct TimingsSpanTestCase {
    pub(crate) description: &'static str,
    pub(crate) stdout: &'static str,
    pub(crate) expected_replayed: Option<&'static str>,
}

/// A project file name and whether the walk keeps its exact bytes.
pub(crate) struct NonUnicodeNameTestCase {
    pub(crate) description: &'static str,
    pub(crate) name: &'static [u8],
    pub(crate) expected_escaped: bool,
}
pub(crate) struct FileComparisonTestCase {
    pub(crate) description: &'static str,
    pub(crate) racy: bool,
    pub(crate) has_digest: bool,
    pub(crate) moved_stamp: bool,
    pub(crate) contents: &'static [u8],
    pub(crate) expected_unchanged: bool,
    pub(crate) expected_reads: usize,
}

#[cfg(unix)]
pub(crate) struct LinkChangeTestCase {
    pub(crate) description: &'static str,
    pub(crate) change: fn(&std::path::Path, &std::path::Path),
    pub(crate) expected_unchanged: bool,
}

#[cfg(unix)]
pub(crate) struct LinkCycleTestCase {
    pub(crate) description: &'static str,
    pub(crate) expected_paths: &'static [&'static str],
}
