//! The exact dbt FQN selector of a node.

use crate::dbt_graph::constants::FQN_SELECTOR_PREFIX;

/// `fqn:<dotted fqn>` when the node has an FQN, else `fallback`.
#[must_use]
pub fn dbt_fqn_selector_term(fqn: &[String], fallback: &str) -> String {
    if fqn.is_empty() {
        return fallback.to_owned();
    }
    format!("{FQN_SELECTOR_PREFIX}{}", fqn.join("."))
}
