use sqlbuild_config::models::ConfigValue;

/// A stored report, a delta report and what splicing the delta into the stored one gives.
pub(crate) struct SpliceTestCase {
    pub(crate) description: &'static str,
    pub(crate) base: &'static str,
    pub(crate) delta: &'static str,
    pub(crate) models: &'static [&'static str],
    pub(crate) tests: &'static [&'static str],
    pub(crate) sources: Option<&'static [&'static str]>,
    /// The spliced report, or `None` when the reports must not line up.
    pub(crate) expected: Option<&'static str>,
}

/// A loaded YAML document kept by the delta compile's document store.
pub(crate) struct DocumentTestCase {
    pub(crate) description: &'static str,
    pub(crate) document: ConfigValue,
}

/// Stored image bytes damaged before they are read back.
pub(crate) struct DamagedImageTestCase {
    pub(crate) description: &'static str,
    pub(crate) damage: fn(&mut Vec<(String, Vec<u8>)>),
    pub(crate) expected_gate: bool,
    pub(crate) expected_image: bool,
}
