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

pub(super) struct HeaderColumnTestCase {
    pub(super) description: &'static str,
    pub(super) columns: Vec<crate::compiled_project::models::HeaderColumnShape>,
    pub(super) expected_blocker: Option<crate::compiled_project::models::PlainModelBlocker>,
}

pub(super) struct SpliceTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) splices: Vec<crate::compiled_project::models::DeclarationSplice>,
    pub(super) expected_sql: &'static str,
    pub(super) expected_output_ranges: Vec<(usize, usize)>,
}

pub(super) struct EnumLiteralTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) integer: bool,
    pub(super) expected_literal: &'static str,
}

pub(super) struct MergeReferencesTestCase {
    pub(super) description: &'static str,
    pub(super) references: Vec<&'static str>,
    pub(super) arguments: Vec<&'static str>,
    pub(super) expected_references: Vec<&'static str>,
}
