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
