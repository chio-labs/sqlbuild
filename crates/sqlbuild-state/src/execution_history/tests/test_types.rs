use crate::execution_history::errors::HistoryErrorKind;
use crate::execution_history::models::{
    Dialect, EventFilterSpec, ProjectionFact, Query, RunFilterSpec, RunRow,
};

pub(crate) struct ProjectionTestCase {
    pub(crate) description: &'static str,
    pub(crate) facts: Vec<ProjectionFact>,
    pub(crate) current: Vec<RunRow>,
    pub(crate) expected_runs: Result<Vec<RunRow>, HistoryErrorKind>,
}

pub(crate) struct QueryTestCase {
    pub(crate) description: &'static str,
    pub(crate) query: Query,
    pub(crate) expected_sql: &'static str,
    pub(crate) expected_param_count: usize,
}

pub(crate) struct RunCursorTestCase {
    pub(crate) description: &'static str,
    pub(crate) dialect: Dialect,
    pub(crate) run: RunRow,
    pub(crate) expected_cursor: &'static str,
    pub(crate) expected_created_at: &'static str,
}

pub(crate) struct CursorRejectionTestCase {
    pub(crate) description: &'static str,
    pub(crate) dialect: Dialect,
    pub(crate) cursor: &'static str,
    pub(crate) expected_message: &'static str,
}

pub(crate) struct EventCursorTestCase {
    pub(crate) description: &'static str,
    pub(crate) cursor: Option<&'static str>,
    pub(crate) expected_position: Result<i64, &'static str>,
}

pub(crate) struct FilterTestCase {
    pub(crate) description: &'static str,
    pub(crate) event_filter: EventFilterSpec,
    pub(crate) run_filter: RunFilterSpec,
    pub(crate) expected_event_error: Option<&'static str>,
    pub(crate) expected_run_error: Option<&'static str>,
}

pub(crate) struct PathTestCase {
    pub(crate) description: &'static str,
    pub(crate) project_dir: Option<&'static str>,
    pub(crate) path: Option<&'static str>,
    pub(crate) busy_timeout_ms: Option<i64>,
    pub(crate) expected_path: Result<&'static str, &'static str>,
}
