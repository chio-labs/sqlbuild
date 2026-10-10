use crate::compiled_project::models::CompiledModelFacts;

pub(super) struct RecordTestCase {
    pub(super) description: &'static str,
    pub(super) recorded: Vec<CompiledModelFacts>,
    pub(super) analysed: &'static str,
    pub(super) expected_order: &'static [&'static str],
    pub(super) expected_query_sql: &'static str,
    pub(super) expected_analysis_recorded: bool,
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

pub(super) struct AnalysisGateTestCase {
    pub(super) description: &'static str,
    pub(super) sql_analysis: bool,
    pub(super) analysis_override: crate::compiled_project::models::AnalysisOverride,
    pub(super) expected_gate: crate::compiled_project::models::AnalysisGate,
}

pub(super) struct DeclarationErrorTestCase {
    pub(super) description: &'static str,
    pub(super) error: crate::compiled_project::errors::DeclarationError,
    pub(super) expected_message: &'static str,
}

pub(super) struct OptOutPositionTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) start: usize,
    pub(super) expected_position: crate::compiled_project::models::TextPosition,
}

pub(super) struct LegacySchemaTestCase {
    pub(super) description: &'static str,
    /// `(schema file, model names)` per legacy schema file.
    pub(super) schema_files: &'static [(&'static str, &'static [&'static str])],
    pub(super) expected_error: Option<&'static str>,
}

pub(super) struct LocatedScanErrorTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) contents: &'static str,
    pub(super) passes: Option<Vec<Vec<crate::compiled_project::models::SplicedSpan>>>,
    pub(super) expected_message: &'static str,
}
