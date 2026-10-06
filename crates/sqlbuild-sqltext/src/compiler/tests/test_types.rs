pub(crate) struct ModelHeaderTokenizationTestCase {
    pub(crate) description: &'static str,
    pub(crate) run: fn() -> bool,
    pub(crate) expected_success: bool,
}

pub(crate) struct StaticSqlOperationTestCase {
    pub(crate) description: &'static str,
    pub(crate) run: fn() -> bool,
    pub(crate) expected_success: bool,
}

pub(crate) struct ModelHeaderMatchTestCase {
    pub(crate) description: &'static str,
    pub(crate) contents: &'static str,
    pub(crate) expected_offsets: Option<(usize, usize, usize)>,
}
