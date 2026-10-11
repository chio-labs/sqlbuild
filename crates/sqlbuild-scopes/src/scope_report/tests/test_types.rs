pub(super) struct ReportTestCase {
    pub(super) description: &'static str,
    pub(super) target: Option<&'static str>,
    pub(super) at: Option<&'static str>,
    pub(super) expected_available: &'static [&'static str],
    pub(super) expected_used: &'static [&'static str],
    pub(super) expected_nearby: &'static [&'static str],
    /// `kind path count` of each scope chain entry.
    pub(super) expected_chain: &'static [&'static str],
    pub(super) expected_complete: bool,
}

pub(super) struct DescendantTestCase {
    pub(super) description: &'static str,
    pub(super) path: &'static str,
    pub(super) ancestor: &'static str,
    pub(super) expected_descendant: bool,
}

pub(super) struct SerializeTestCase {
    pub(super) description: &'static str,
    pub(super) folder: &'static str,
    pub(super) expected_json: &'static str,
}
