/// Elapsed milliseconds and Python's `f"{ms / 1000:.1f}"`.
pub(crate) struct TenthsTestCase {
    pub(crate) description: &'static str,
    pub(crate) milliseconds: i64,
    pub(crate) expected_text: &'static str,
}
