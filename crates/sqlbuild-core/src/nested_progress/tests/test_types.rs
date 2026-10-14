use crate::nested_progress::models::NestedItem;

pub(super) struct NestedItemTestCase {
    pub(super) description: &'static str,
    pub(super) item: NestedItem,
    pub(super) expected_text: &'static str,
}

pub(super) struct SpinnerTestCase {
    pub(super) description: &'static str,
    pub(super) running: Vec<String>,
    pub(super) columns: usize,
    pub(super) expected_text: &'static str,
}
