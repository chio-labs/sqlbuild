use crate::sql_scan::models::Unclosed;

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

pub(crate) struct TopLevelScanTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_unions: Result<Vec<&'static str>, String>,
    pub(crate) expected_commas: Result<Vec<&'static str>, String>,
    pub(crate) expected_from: Result<Option<usize>, String>,
}

pub(crate) type CteSlices = Option<(Vec<(&'static str, &'static str)>, &'static str)>;

pub(crate) struct CteSliceTestCase {
    pub(crate) description: &'static str,
    pub(crate) dialect: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_slices: Result<CteSlices, Unclosed>,
}

pub(crate) struct CteRenameTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) renamed_index: usize,
    pub(crate) expected_sql: Option<&'static str>,
}
