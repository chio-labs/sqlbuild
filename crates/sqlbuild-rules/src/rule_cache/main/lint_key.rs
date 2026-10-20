//! `lint_key`: the lint settings part of every SQL rule cache key.

use crate::rule_cache::_helpers::digest::field_digest;
use crate::rule_cache::constants::LINT_KEY_KIND;
use crate::rule_cache::models::LintKeyInput;

fn key_sets(keys: &[Vec<String>]) -> String {
    let mut sets: Vec<String> = Vec::with_capacity(keys.len());
    for columns in keys {
        sets.push(columns.join("\u{1f}"));
    }
    sets.join("\u{1d}")
}

/// A digest of the dialect, literal and ranking limits and sorted relation keys.
#[must_use]
pub fn lint_key(input: &LintKeyInput) -> String {
    let mut relation_keys: Vec<(String, Vec<Vec<String>>)> = input.relation_keys.clone();
    relation_keys.sort();
    let relations: String = relation_keys
        .iter()
        .map(|(relation, keys)| format!("{relation}\u{1e}{}", key_sets(keys)))
        .collect::<Vec<_>>()
        .join("\u{1c}");
    field_digest(
        LINT_KEY_KIND,
        &[
            &input.dialect,
            &input.max_literal_length.to_string(),
            &input.max_ranking_order_by.to_string(),
            &relations,
        ],
    )
}
