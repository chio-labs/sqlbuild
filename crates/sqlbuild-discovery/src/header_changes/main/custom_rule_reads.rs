//! Whether a custom rule reads what changed in a model header.

use std::collections::BTreeSet;

/// Whether a custom rule reads a fact of this model that the changed header keys decide.
#[must_use]
pub fn custom_rule_reads(
    fact_digests: &[(Vec<String>, String)],
    model: (&str, &str),
    changed: &BTreeSet<String>,
) -> Option<String> {
    let (path, name) = model;
    for (key, _) in fact_digests {
        let Some((fact, arguments)) = key.split_first() else {
            continue;
        };
        if !arguments
            .iter()
            .any(|argument| argument == path || argument == name)
        {
            continue;
        }
        let reads: &[&str] = match fact.as_str() {
            "contracts.enforced" | "contract" => &["contract"],
            "contracts.grain" | "grain" => &["contract", "columns"],
            "columns.declared" | "columns.names" => &["columns", "dynamic_columns"],
            "materialized" => &["materialized"],
            "tests.for_model" | "audits.for_model" => &["audits", "columns"],
            _ => &[],
        };
        if let Some(key) = reads.iter().find(|key| changed.contains(**key)) {
            return Some(format!("a custom rule reads {name}'s {key}"));
        }
    }
    None
}
