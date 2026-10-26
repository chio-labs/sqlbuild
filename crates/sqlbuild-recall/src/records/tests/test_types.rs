use crate::records::models::{RecallRow, RecallValue};

pub(crate) struct RecordIdTestCase {
    pub(crate) description: &'static str,
    pub(crate) record_id: String,
    pub(crate) expected_record_id: &'static str,
}

pub(crate) struct TimestampTestCase {
    pub(crate) description: &'static str,
    pub(crate) micros: u64,
    pub(crate) expected_text: &'static str,
}

pub(crate) struct ParseTimestampTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: &'static str,
    pub(crate) expected_micros: Option<u64>,
}

pub(crate) struct ContentHashTestCase {
    pub(crate) description: &'static str,
    pub(crate) left: Vec<(&'static str, RecallValue)>,
    pub(crate) right: Vec<(&'static str, RecallValue)>,
    pub(crate) expected_equal: bool,
}

pub(crate) struct RowColumnsTestCase {
    pub(crate) description: &'static str,
    pub(crate) row: RecallRow,
    pub(crate) expected_columns: Vec<(&'static str, RecallValue)>,
}

pub(crate) struct RejectedInputTestCase {
    pub(crate) description: &'static str,
    pub(crate) json: &'static str,
    pub(crate) expected_rejected: bool,
}

pub(crate) struct DiagnosticTestCase {
    pub(crate) description: &'static str,
    pub(crate) json: &'static str,
    pub(crate) sequence: u64,
    pub(crate) expected_fields: &'static str,
    pub(crate) expected_run_id: Option<&'static str>,
}

pub(crate) struct OriginTestCase {
    pub(crate) description: &'static str,
    pub(crate) has_external_context: bool,
    pub(crate) environment: Vec<(&'static str, &'static str)>,
    pub(crate) expected_origin: &'static str,
}

pub(crate) struct CommandModeTestCase {
    pub(crate) description: &'static str,
    pub(crate) command: Option<&'static str>,
    pub(crate) no_connection: bool,
    pub(crate) expected_mode: Option<&'static str>,
}
