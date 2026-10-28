use crate::json::models::JsonValue;
use crate::query_command::models::{QueryDisplay, QueryLayout};

pub(super) struct DisplayTestCase {
    pub(super) description: &'static str,
    pub(super) display: QueryDisplay,
    pub(super) layout: QueryLayout,
    pub(super) expected_text: &'static str,
}

pub(super) struct FooterTestCase {
    pub(super) description: &'static str,
    pub(super) row_count: usize,
    pub(super) expected_footer: &'static str,
}

pub(super) struct JsonTestCase {
    pub(super) description: &'static str,
    pub(super) columns: Vec<String>,
    pub(super) rows: Vec<Vec<JsonValue>>,
    pub(super) expected_json: &'static str,
}

pub(super) struct DagTestCase {
    pub(super) description: &'static str,
    pub(super) counts: (usize, usize, usize),
    pub(super) expected_text: &'static str,
}
