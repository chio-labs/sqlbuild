//! Classify executed SQL by its effect on cached relation existence and columns.

use crate::ddl_effects::_helpers::code_text::{LexicalMode, code_text};
use crate::ddl_effects::_helpers::relations::{all_relations, code_effect};
use crate::ddl_effects::models::StatementMetadataEffect;

/// Which cached relation names `sql` may have changed; readings that disagree change all.
#[must_use]
pub fn statement_metadata_effect(sql: &str) -> StatementMetadataEffect {
    let backslash_modes: &[bool] = if sql.contains('\\') {
        &[false, true]
    } else {
        &[false]
    };
    let bracket_modes: &[bool] = if sql.contains('[') {
        &[false, true]
    } else {
        &[false]
    };
    let mut effects: Vec<StatementMetadataEffect> = Vec::new();
    for backslash_escapes in backslash_modes {
        for bracket_identifiers in bracket_modes {
            let mode: LexicalMode = LexicalMode {
                backslash_escapes: *backslash_escapes,
                bracket_identifiers: *bracket_identifiers,
            };
            let effect: StatementMetadataEffect = code_effect(code_text(sql, mode).as_deref());
            if !effects.contains(&effect) {
                effects.push(effect);
            }
        }
    }
    match <[StatementMetadataEffect; 1]>::try_from(effects) {
        Ok([effect]) => effect,
        Err(_) => all_relations(),
    }
}
