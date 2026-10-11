//! The problem with one reference an audit body makes.

use crate::audits::constants::{DBT_REF_KIND, REF_KIND, SEED_KIND, SOURCE_KIND};
use crate::functions::models::KnownResources;

/// What is wrong with the `kind` reference to `name`, or `None` when it resolves.
pub(crate) fn reference_problem(
    kind: &str,
    name: &str,
    known: &KnownResources<'_>,
) -> Option<String> {
    match kind {
        DBT_REF_KIND => Some(format!(
            "may not use {}; audit dbt model checks belong in dbt",
            example_call("__dbt_ref", name)
        )),
        REF_KIND if !known.models.contains(name) && known.seeds.contains(name) => Some(format!(
            "references seed '{name}' with __ref(...). Use {} for seed references; __ref only \
             resolves models.",
            example_call("__seed", name)
        )),
        REF_KIND if !known.models.contains(name) => {
            Some(format!("references unknown model '{name}'"))
        }
        SEED_KIND if !known.seeds.contains(name) => {
            Some(format!("references unknown seed '{name}'"))
        }
        SOURCE_KIND if !known.sources.contains(name) => {
            Some(format!("references unknown source '{name}'"))
        }
        _ => None,
    }
}

/// `SqlReferenceKind.example_call(name, quote='"')`.
fn example_call(function: &str, name: &str) -> String {
    format!("{function}(\"{}\")", name.replace('"', "\"\""))
}
