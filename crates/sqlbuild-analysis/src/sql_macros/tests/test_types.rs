use std::collections::HashMap;
use std::sync::Arc;

use crate::sql_macros::models::SqlMacroDefinition;

pub(super) struct ExpansionTestCase {
    pub(super) description: &'static str,
    pub(super) adapter: &'static str,
    pub(super) macros: &'static [(&'static str, &'static str)],
    pub(super) sql: &'static str,
    pub(super) expected_sql: &'static str,
}

pub(super) struct ExpansionErrorTestCase {
    pub(super) description: &'static str,
    pub(super) adapter: &'static str,
    pub(super) macros: &'static [(&'static str, &'static str)],
    pub(super) sql: &'static str,
    pub(super) expected_code: &'static str,
    pub(super) expected_message: &'static str,
}

pub(super) struct DefinitionErrorTestCase {
    pub(super) description: &'static str,
    pub(super) source: &'static str,
    pub(super) expected_code: &'static str,
    pub(super) expected_message: &'static str,
}

pub(super) struct DefinitionTestCase {
    pub(super) description: &'static str,
    pub(super) source: &'static str,
    pub(super) expected_labels: &'static [&'static str],
    pub(super) expected_form: &'static str,
    pub(super) expected_body_position: (usize, usize),
}

pub(super) struct CycleTestCase {
    pub(super) description: &'static str,
    pub(super) calls: &'static [(&'static str, &'static [&'static str])],
    pub(super) expected_cycle: Option<&'static [&'static str]>,
}

/// A host serving parsed macros and fixed declaration values, for one adapter.
pub(super) struct FakeHost {
    pub(super) definitions: HashMap<String, Arc<SqlMacroDefinition>>,
    pub(super) adapter: &'static str,
}
