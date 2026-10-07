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
