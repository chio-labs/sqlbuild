use sqlbuild_analysis::assembly::analysis_session::models::LineageFacts;

use crate::types::ProjectHost;

/// A host that keeps nothing beside the records.
#[derive(Debug)]
pub(super) struct TestHost;

impl ProjectHost for TestHost {
    type ModelInput = ();
    type Schema = ();
    type CompiledModel = ();
    type Analysis = ();
    type AttachedSource = ();
    type Source = ();
    type AttachedFunction = ();
    type Function = ();
    type AttachedAudit = ();
    type Audit = ();
    type Seed = ();
}

pub(super) struct LineageTestCase {
    pub(super) description: &'static str,
    pub(super) lineage: Option<LineageFacts>,
    pub(super) expected_outputs: Option<Vec<&'static str>>,
    pub(super) expected_edge_count: Option<usize>,
}

pub(super) struct ProjectInputTestCase {
    pub(super) description: &'static str,
    pub(super) retained: &'static [&'static str],
    pub(super) recorded_schemas: &'static [&'static str],
    pub(super) read_index: usize,
    pub(super) expected_indexes: Vec<usize>,
    pub(super) expected_name: Option<&'static str>,
    pub(super) expected_schema_column: Option<&'static str>,
}
