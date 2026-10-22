//! Aspect comparison and the words reasons use for aspects and kinds.

use crate::definition_changes::constants::{ASPECT_LABELS, KIND_LABELS};
use crate::definition_changes::models::NodeDefinition;

fn aspect_rank(aspect: &str) -> usize {
    ASPECT_LABELS
        .iter()
        .position(|(name, _)| *name == aspect)
        .unwrap_or(ASPECT_LABELS.len())
}

/// The aspects present on either side whose digests differ, in reason order.
pub(crate) fn changed_aspects(base: &NodeDefinition, current: &NodeDefinition) -> Vec<String> {
    let mut aspects: Vec<String> = base
        .aspects
        .keys()
        .chain(current.aspects.keys())
        .filter(|aspect| base.aspects.get(*aspect) != current.aspects.get(*aspect))
        .cloned()
        .collect();
    aspects.sort_by(|left, right| {
        aspect_rank(left)
            .cmp(&aspect_rank(right))
            .then(left.cmp(right))
    });
    aspects.dedup();
    aspects
}

/// How an aspect reads in a reason.
pub(crate) fn aspect_label(aspect: &str) -> &str {
    ASPECT_LABELS
        .iter()
        .find(|(name, _)| *name == aspect)
        .map_or(aspect, |(_, label)| label)
}

/// The singular and plural words of a node kind.
pub(crate) fn kind_words(kind: &str) -> (&str, String) {
    KIND_LABELS
        .iter()
        .find(|(name, _, _)| *name == kind)
        .map_or_else(
            || (kind, format!("{kind}s")),
            |(_, singular, plural)| (*singular, (*plural).to_owned()),
        )
}

/// `a`, `a and b`, `a, b and c`.
pub(crate) fn joined(words: &[String]) -> String {
    match words {
        [] => String::new(),
        [only] => only.clone(),
        [init @ .., last] => format!("{} and {last}", init.join(", ")),
    }
}
