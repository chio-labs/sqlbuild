//! Classify a model's change.

use crate::planner_changes::models::{BackfillFacts, ChangeKind};

/// The change kind by precedence: query, then called functions, schema, config, else no change.
pub fn model_change_kind(facts: BackfillFacts) -> ChangeKind {
    if facts.query_changed {
        ChangeKind::QueryChanged
    } else if facts.functions_changed {
        ChangeKind::FunctionChanged
    } else if facts.schema_changed {
        ChangeKind::SchemaChanged
    } else if facts.config_changed {
        ChangeKind::ConfigChanged
    } else {
        ChangeKind::NoChange
    }
}
