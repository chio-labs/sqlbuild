pub(crate) struct EvidenceTestCase {
    pub(crate) description: &'static str,
    pub(crate) project: &'static str,
    pub(crate) test_source: &'static str,
    pub(crate) expected_closure: Vec<&'static str>,
    pub(crate) expected_cases: Vec<(usize, usize, &'static str)>,
}

pub(crate) struct AllowedImportTestCase {
    pub(crate) description: &'static str,
    pub(crate) module: &'static str,
    pub(crate) expected_allowed: bool,
}

pub(crate) struct DisallowedImportTestCase {
    pub(crate) description: &'static str,
    pub(crate) source: &'static str,
    pub(crate) expected_import: Result<
        Option<crate::rule_evidence::models::DisallowedImport>,
        crate::rule_evidence::models::UnparsedSource,
    >,
}

pub(crate) struct ProjectClosureTestCase {
    pub(crate) description: &'static str,
    pub(crate) files: Vec<(&'static str, &'static str)>,
    pub(crate) source: &'static str,
    pub(crate) expected_closure: Vec<&'static str>,
}
