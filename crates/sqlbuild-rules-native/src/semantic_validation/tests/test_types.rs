pub(crate) struct SemanticValidationTestCase {
    pub(crate) description: &'static str,
    pub(crate) request: &'static str,
    pub(crate) expected_complete: bool,
}

pub(crate) struct SemanticValidationBatchTestCase {
    pub(crate) description: &'static str,
    pub(crate) request: &'static str,
    pub(crate) expected_validity: [bool; 2],
}

pub(crate) struct UnsupportedFunctionTestCase {
    pub(crate) description: &'static str,
    pub(crate) dialect: polyglot_sql::DialectType,
    pub(crate) sql: &'static str,
    pub(crate) expected_calls: &'static [(&'static str, &'static str)],
}

pub(crate) struct LocatedFunctionDiagnosticTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_message: &'static str,
    pub(crate) expected_location: (Option<usize>, Option<usize>),
    pub(crate) expected_span: (Option<usize>, Option<usize>),
}
