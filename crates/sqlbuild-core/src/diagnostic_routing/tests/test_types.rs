use crate::diagnostic_routing::models::{RecordFacts, RouteOptions, ThirdPartyConsoleForm};

pub(super) struct InternalLoggerTestCase {
    pub(super) description: &'static str,
    pub(super) name: &'static str,
    pub(super) expected_internal: bool,
}

pub(super) struct RouteTestCase {
    pub(super) description: &'static str,
    pub(super) options: RouteOptions,
    pub(super) record: RecordFacts,
    pub(super) expected_admitted: bool,
}

pub(super) struct ComputeLogTestCase {
    pub(super) description: &'static str,
    pub(super) record: RecordFacts,
    pub(super) include_sql_text: bool,
    pub(super) expected_admitted: bool,
}

pub(super) struct SeverityTestCase {
    pub(super) description: &'static str,
    pub(super) level: i64,
    pub(super) expected_severity: &'static str,
}

pub(super) struct DigestTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_digest: &'static str,
}

pub(super) struct ConsoleFormTestCase {
    pub(super) description: &'static str,
    pub(super) level: i64,
    pub(super) expected_form: ThirdPartyConsoleForm,
}

pub(super) struct SummaryLineTestCase {
    pub(super) description: &'static str,
    pub(super) message: &'static str,
    pub(super) expected_line: &'static str,
}

pub(super) struct ProjectSourceTestCase {
    pub(super) description: &'static str,
    pub(super) pathname: &'static str,
    pub(super) expected_project: bool,
}
