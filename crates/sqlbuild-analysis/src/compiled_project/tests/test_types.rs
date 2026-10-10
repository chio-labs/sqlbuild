use crate::compiled_project::models::CompiledModelFacts;

pub(super) struct RecordTestCase {
    pub(super) description: &'static str,
    pub(super) recorded: Vec<CompiledModelFacts>,
    pub(super) analysed: &'static str,
    pub(super) expected_order: &'static [&'static str],
    pub(super) expected_query_sql: &'static str,
    pub(super) expected_analysis_recorded: bool,
}
