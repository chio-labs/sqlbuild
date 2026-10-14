//! dbt selectors for the dbt models selected SQLBuild models need.

use std::collections::{BTreeSet, HashSet};

use crate::dbt_graph::main::dbt_fqn_selector_term::dbt_fqn_selector_term;
use crate::dbt_plan::models::DbtReferencedModel;

/// Sorted, distinct `+<fqn selector>` terms for referenced dbt models that are required.
#[must_use]
pub fn dbt_required_selector_terms(
    referenced: &[DbtReferencedModel],
    required_unique_ids: &[String],
) -> Vec<String> {
    let required: HashSet<&str> = required_unique_ids.iter().map(String::as_str).collect();
    let terms: BTreeSet<String> = referenced
        .iter()
        .filter(|model| required.contains(model.unique_id.as_str()))
        .map(|model| format!("+{}", dbt_fqn_selector_term(&model.fqn, &model.name)))
        .collect();
    terms.into_iter().collect()
}
