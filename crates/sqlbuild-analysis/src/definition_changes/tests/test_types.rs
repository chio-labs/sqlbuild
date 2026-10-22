use crate::definition_changes::models::{DefinitionSnapshot, ExecutedItem, SelectedItem};

/// One expected changed node: key, changed aspects, added, renamed-from name.
pub(crate) type ExpectedChange = (
    &'static str,
    &'static [&'static str],
    bool,
    Option<&'static str>,
);

pub(crate) struct CompareTestCase {
    pub(crate) description: &'static str,
    pub(crate) base: DefinitionSnapshot,
    pub(crate) current: DefinitionSnapshot,
    pub(crate) expected_changes: &'static [ExpectedChange],
    /// `(base key, current key)`.
    pub(crate) expected_renamed: &'static [(&'static str, &'static str)],
    /// `kind name` of each deleted node.
    pub(crate) expected_deleted: &'static [&'static str],
    pub(crate) expected_summary: &'static str,
}

pub(crate) struct SelectionReasonTestCase {
    pub(crate) description: &'static str,
    pub(crate) current: DefinitionSnapshot,
    pub(crate) item: ExecutedItem,
    pub(crate) expected_reasons: &'static [&'static str],
}

pub(crate) struct SelectionReportTestCase {
    pub(crate) description: &'static str,
    pub(crate) summary: &'static str,
    pub(crate) nouns: (&'static str, &'static str),
    pub(crate) total: usize,
    pub(crate) selected: Vec<SelectedItem>,
    pub(crate) explain: bool,
    pub(crate) expected_text: &'static str,
}

pub(crate) struct SnapshotJsonTestCase {
    pub(crate) description: &'static str,
    /// Turns the stored text of the base orders snapshot into the text to read back.
    pub(crate) stored: fn(String) -> String,
    pub(crate) expected_snapshot: Option<DefinitionSnapshot>,
}

pub(crate) struct SqlDigestTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_same_as_original: bool,
}

pub(crate) struct SelectionJsonTestCase {
    pub(crate) description: &'static str,
    pub(crate) selected: Vec<crate::definition_changes::models::SelectedItem>,
    pub(crate) expected_json: serde_json::Value,
}
