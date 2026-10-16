use crate::microbatches::models::{
    BoundInterval, CompletionFact, CoveragePiece, MicrobatchEventIdentity, ReplayState,
};

pub(crate) struct CoverageTestCase {
    pub(crate) description: &'static str,
    pub(crate) completions: Vec<CompletionFact>,
    pub(crate) expected: Vec<BoundInterval>,
    pub(crate) expected_segments: Vec<(&'static str, &'static str, usize)>,
    pub(crate) expected_frontier: Option<&'static str>,
    pub(crate) expected_known_missing: Vec<(&'static str, &'static str)>,
    pub(crate) expected_unaccounted: Vec<(&'static str, &'static str)>,
}

pub(crate) struct ReplayTestCase {
    pub(crate) description: &'static str,
    pub(crate) required: Option<&'static str>,
    pub(crate) coverage: Vec<CoveragePiece>,
    pub(crate) expected_state: ReplayState,
    pub(crate) expected_missing: Vec<usize>,
}

pub(crate) struct EventIdTestCase {
    pub(crate) description: &'static str,
    pub(crate) identity: MicrobatchEventIdentity,
    pub(crate) expected_id: &'static str,
}

pub(crate) struct InsertManyTestCase {
    pub(crate) description: &'static str,
    pub(crate) rows: Vec<Vec<String>>,
    pub(crate) expected_sql: &'static str,
}
