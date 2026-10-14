//! Model names that participate in a migration identity.

use crate::planner_migrations::_helpers::proofs::fingerprint::metadata;
use crate::planner_migrations::constants::REF_MARKER;
use regex::Regex;
use std::collections::BTreeSet;

/// Every query reference and configured cursor-input name.
pub fn migration_ref_names(sql: &str, metadata_json: &str) -> Result<BTreeSet<String>, String> {
    let marker = Regex::new(REF_MARKER).map_err(|error| error.to_string())?;
    let mut names: BTreeSet<String> = BTreeSet::new();
    for captures in marker.captures_iter(sql) {
        if let Some(value) = captures.get(1).or_else(|| captures.get(2)) {
            names.insert(value.as_str().to_owned());
        }
    }
    if let Some(inputs) = metadata(metadata_json)["config"]["cursor_inputs"].as_object() {
        names.extend(inputs.keys().cloned());
    }
    Ok(names)
}
