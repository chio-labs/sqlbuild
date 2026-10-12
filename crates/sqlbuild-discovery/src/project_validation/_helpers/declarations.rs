//! Duplicate schema declarations and logical relation names shared across resource kinds.

use std::collections::HashMap;

use crate::project_validation::_helpers::conflicts::{
    conflict, named, schema_seeds, source_entries, unique_named,
};
use crate::project_validation::models::{NamedPath, ProjectFacts, ValidationFailure};

/// Reject duplicate schema model and seed declarations, then shared relation names.
pub(crate) fn validate_declarations(facts: &ProjectFacts) -> Result<(), ValidationFailure> {
    let mut schema_models: Vec<NamedPath> = Vec::new();
    for schema in &facts.schemas {
        for name in &schema.model_names {
            schema_models.push(named(name, &schema.path));
        }
    }
    unique_named(&schema_models, |name, existing, path| {
        format!(
            "Duplicate schema.yml model declaration found for '{name}' in {existing} and {path}"
        )
    })?;
    unique_named(&schema_seeds(facts), |name, existing, path| {
        format!("Duplicate seed declaration found for '{name}' in {existing} and {path}")
    })?;
    unique_logical_relation_names(facts)
}

fn unique_logical_relation_names(facts: &ProjectFacts) -> Result<(), ValidationFailure> {
    let mut seen: HashMap<String, (&'static str, String)> = HashMap::new();
    for model in &facts.models {
        seen.insert(model.file.name.clone(), ("model", model.file.path.clone()));
    }
    let sources = source_entries(facts)
        .into_iter()
        .map(|entry| ("source", entry));
    let seeds = schema_seeds(facts).into_iter().map(|seed| ("seed", seed));
    for (kind, NamedPath { name, path }) in sources.chain(seeds) {
        if let Some((existing_kind, existing_path)) = seen.get(&name) {
            return Err(conflict(format!(
                "Logical relation name '{name}' is declared as both {existing_kind} in \
                 {existing_path} and {kind} in {path}"
            )));
        }
        seen.insert(name, (kind, path));
    }
    Ok(())
}
