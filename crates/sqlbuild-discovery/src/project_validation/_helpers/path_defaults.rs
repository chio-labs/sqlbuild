//! Every `path_defaults` key must match at least one model path.

use std::collections::HashSet;

use sqlbuild_model_config::path_defaults::main::matched_path_default_keys::matched_path_default_keys;

use crate::models::{DiscoveryFailure, FailureKind};
use crate::project_validation::_helpers::conflicts::conflict;
use crate::project_validation::constants::{CURRENT_DIRECTORY, KNOWN_FOLDER_LIMIT, MODELS_PREFIX};
use crate::project_validation::models::{ProjectFacts, ValidationFailure};

pub(crate) fn validate_path_defaults(facts: &ProjectFacts) -> Result<(), ValidationFailure> {
    if facts.path_default_keys.is_empty() {
        return Ok(());
    }
    let model_paths: Vec<String> = facts
        .models
        .iter()
        .map(|model| {
            let path: String = model.file.path.replace('\\', "/");
            path.strip_prefix(MODELS_PREFIX)
                .map_or(path.clone(), str::to_owned)
        })
        .collect();
    let mut matched: HashSet<String> = HashSet::new();
    for model_path in &model_paths {
        let keys: Vec<String> = matched_path_default_keys(model_path, &facts.path_default_keys)
            .map_err(|error| {
                ValidationFailure::Discovery(DiscoveryFailure {
                    kind: FailureKind::Conflict,
                    message: error.message,
                    help: error.help,
                })
            })?;
        matched.extend(keys);
    }
    for key in &facts.path_default_keys {
        if matched.contains(key) {
            continue;
        }
        let mut folders: Vec<String> = model_paths
            .iter()
            .map(|path| parent_folder(path))
            .filter(|folder| folder != CURRENT_DIRECTORY)
            .collect::<HashSet<String>>()
            .into_iter()
            .collect();
        folders.sort();
        let known: String = if folders.is_empty() {
            "<none>".to_owned()
        } else {
            folders
                .iter()
                .take(KNOWN_FOLDER_LIMIT)
                .cloned()
                .collect::<Vec<_>>()
                .join(", ")
        };
        return Err(conflict(format!(
            "path_defaults['{key}'] does not match any model paths. Known model folders include: \
             {known}"
        )));
    }
    Ok(())
}

/// `str(Path(path).parent)` for a discovered POSIX relative path.
fn parent_folder(path: &str) -> String {
    let parts: Vec<&str> = path
        .split('/')
        .filter(|part| !part.is_empty() && *part != CURRENT_DIRECTORY)
        .collect();
    match parts.split_last() {
        Some((_, parents)) if !parents.is_empty() => parents.join("/"),
        _ => CURRENT_DIRECTORY.to_owned(),
    }
}
