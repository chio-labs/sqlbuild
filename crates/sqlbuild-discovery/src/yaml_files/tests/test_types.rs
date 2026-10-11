use crate::yaml_files::models::YamlFileOutcome;

pub(super) struct YamlFileTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static [u8],
    pub(super) expected_outcome: YamlFileOutcome,
}

pub(super) struct YamlTextTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    /// The failure message and help, or `None` when the document loads.
    pub(super) expected_failure: Option<(&'static str, Option<&'static str>)>,
}

pub(super) struct EntryLinesTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    /// The line of each named entry the case checks; `None` where no entry has the name.
    pub(super) expected_lines: &'static [(&'static str, Option<usize>)],
}
