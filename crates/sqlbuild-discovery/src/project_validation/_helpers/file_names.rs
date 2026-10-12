//! Duplicate and reserved names among model, scenario and source files.

use std::collections::HashMap;

use crate::project_validation::_helpers::conflicts::{conflict, source_entries, unique_named};
use crate::project_validation::constants::RESERVED_MODEL_NAMES;
use crate::project_validation::models::{ModelFact, NamedPath, ProjectFacts, ValidationFailure};

/// Reject reserved or duplicate model names, then duplicate scenario and source names.
pub(crate) fn validate_file_names(facts: &ProjectFacts) -> Result<(), ValidationFailure> {
    unique_model_file_names(&facts.models)?;
    unique_named(&facts.scenarios, |name, existing, path| {
        format!("Duplicate scenario file name found for '{name}' in {existing} and {path}")
    })?;
    unique_named(&source_entries(facts), |name, existing, path| {
        format!("Duplicate source declaration found for '{name}' in {existing} and {path}")
    })
}

fn unique_model_file_names(models: &[ModelFact]) -> Result<(), ValidationFailure> {
    let mut seen: HashMap<&str, &str> = HashMap::new();
    for model in models {
        let NamedPath { name, path } = &model.file;
        if RESERVED_MODEL_NAMES.contains(&name.as_str()) {
            return Err(conflict(format!(
                "Model name '{name}' in {path} is reserved by SQLBuild for compiled output structure"
            )));
        }
        if let Some(existing) = seen.get(name.as_str()) {
            return Err(conflict(format!(
                "Duplicate model file name found for '{name}' in {existing} and {path}"
            )));
        }
        seen.insert(name, path);
    }
    Ok(())
}
