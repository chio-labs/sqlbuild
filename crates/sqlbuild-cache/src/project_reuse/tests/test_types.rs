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
    /// Output files left without a slot before storing, each with its age in seconds.
    pub(crate) orphaned_outputs: &'static [(&'static str, u64)],
    pub(crate) expected_kept: &'static [&'static str],
}

/// A stored compile whose slot carries an extra section when its inputs are refreshed.
pub(crate) struct SlotRefreshTestCase {
    pub(crate) description: &'static str,
    pub(crate) extra_section: (&'static str, &'static [u8]),
    pub(crate) expected_output_rewritten: bool,
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
