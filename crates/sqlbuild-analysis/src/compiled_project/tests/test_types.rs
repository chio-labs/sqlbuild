use crate::compiled_project::models::CompiledModelFacts;

pub(super) struct RecordTestCase {
    pub(super) description: &'static str,
    pub(super) recorded: Vec<CompiledModelFacts>,
    pub(super) analysed: &'static str,
    pub(super) expected_order: &'static [&'static str],
    pub(super) expected_query_sql: &'static str,
    pub(super) expected_analysis_recorded: bool,
}

pub(super) struct PlainBlockerTestCase {
    pub(super) description: &'static str,
    pub(super) check: crate::compiled_project::models::PlainModelCheck,
    pub(super) expected_blocker: Option<crate::compiled_project::models::PlainModelBlocker>,
}

pub(super) struct PlainFactsTestCase {
    pub(super) description: &'static str,
    pub(super) model_description: Option<&'static str>,
    pub(super) expected_schema: Option<crate::compiled_project::models::ModelSchemaFact>,
}
