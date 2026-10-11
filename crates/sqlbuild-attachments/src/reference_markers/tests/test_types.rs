use sqlbuild_sqltext::sql_scan::models::Unclosed;

pub(super) struct ReferenceMarkerTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_marker: Result<Option<usize>, Unclosed>,
}
