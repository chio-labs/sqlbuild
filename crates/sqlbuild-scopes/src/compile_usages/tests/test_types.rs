use crate::compile_usages::models::{DependencySource, NamedRecord, SchemaDeclaration};
use std::collections::HashMap;

/// Schemas, their indexed records, and the usages and S006 messages they yield.
pub(super) struct SchemaScopeUsagesTestCase {
    pub(super) description: &'static str,
    pub(super) schemas: fn() -> Vec<SchemaDeclaration>,
    pub(super) schema_records: fn() -> HashMap<String, NamedRecord>,
    pub(super) enum_records: fn() -> HashMap<String, NamedRecord>,
    pub(super) expected_usages: &'static [(usize, usize)],
    pub(super) expected_messages: &'static [&'static str],
}

/// Declarations with their own dependencies, collected usages, and the merged sources.
pub(super) struct MergedDependenciesTestCase {
    pub(super) description: &'static str,
    pub(super) declarations: &'static [(&'static str, Option<&'static [&'static str]>)],
    pub(super) usages: &'static [(Option<&'static str>, &'static str)],
    pub(super) expected_sources: &'static [Option<&'static [DependencySource]>],
}

/// Keys and the positions of their first occurrences.
pub(super) struct DistinctPositionsTestCase {
    pub(super) description: &'static str,
    pub(super) keys: &'static [&'static str],
    pub(super) expected_positions: &'static [usize],
}
