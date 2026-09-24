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

pub(crate) struct SqlTestExtractionTestCase {
    pub(crate) description: &'static str,
    pub(crate) run: fn() -> bool,
    pub(crate) expected_success: bool,
}

pub(crate) struct SqlTestPlanningTestCase {
    pub(crate) description: &'static str,
    pub(crate) run: fn() -> bool,
    pub(crate) expected_success: bool,
}

pub(crate) struct SqlTestRenderingTestCase {
    pub(crate) description: &'static str,
    pub(crate) run: fn() -> bool,
    pub(crate) expected_success: bool,
}

pub(crate) struct ExpectedColumnsTestCase {
    pub(crate) description: &'static str,
    pub(crate) dialect: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_columns: Option<&'static [&'static str]>,
}
