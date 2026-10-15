use crate::migration_values::models::{ColumnDecisionTraits, DecisionTraits, ModelMigrationFacts};

pub(super) struct DecisionTestCase {
    pub(super) description: &'static str,
    pub(super) decision: &'static str,
    pub(super) expected_traits: DecisionTraits,
}

pub(super) struct ColumnDecisionTestCase {
    pub(super) description: &'static str,
    pub(super) decision: &'static str,
    pub(super) expected_traits: ColumnDecisionTraits,
}

pub(super) struct BlocksBuildTestCase {
    pub(super) description: &'static str,
    pub(super) facts: ModelMigrationFacts,
    pub(super) expected_blocks: bool,
}

pub(super) struct TransitionTestCase {
    pub(super) description: &'static str,
    pub(super) types: (bool, Option<bool>),
    pub(super) expected_transition: Option<&'static str>,
}
