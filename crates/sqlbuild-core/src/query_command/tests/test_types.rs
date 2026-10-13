use crate::json::models::JsonValue;
use crate::query_command::models::QueryDisplay;

pub(super) struct DisplayTestCase {
    pub(super) description: &'static str,
    pub(super) display: QueryDisplay,
    pub(super) expected_long: &'static str,
    pub(super) expected_table: &'static str,
}

pub(super) struct CsvTestCase {
    pub(super) description: &'static str,
    pub(super) columns: Vec<String>,
    pub(super) rows: Vec<Vec<String>>,
    pub(super) expected_csv: &'static str,
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
