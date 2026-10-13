use crate::load_command::models::{LoadEntry, LoadResultText};

pub(super) struct SelectionTestCase {
    pub(super) description: &'static str,
    pub(super) select: &'static [&'static str],
    pub(super) exclude: &'static [&'static str],
    pub(super) expected_entries: Result<Vec<LoadEntry>, &'static str>,
}

pub(super) struct ReferenceTestCase {
    pub(super) description: &'static str,
    pub(super) selected: Vec<(String, Option<String>)>,
    pub(super) expected_loaders: &'static [&'static str],
}

pub(super) struct ResultLineTestCase {
    pub(super) description: &'static str,
    pub(super) result: LoadResultText,
    pub(super) use_color: bool,
    pub(super) expected_text: &'static str,
}

pub(super) struct FooterTestCase {
    pub(super) description: &'static str,
    pub(super) results: Vec<LoadResultText>,
    pub(super) expected_text: &'static str,
    pub(super) expected_exit_code: i32,
}
