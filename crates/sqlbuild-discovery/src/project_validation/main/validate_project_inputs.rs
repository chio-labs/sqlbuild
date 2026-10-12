//! Python's `validate_discovered_inputs`: cross-file conflicts across discovered project inputs.

use std::collections::{HashMap, HashSet};

use crate::models::{DiscoveryFailure, FailureKind};
use crate::project_validation::_helpers::identities::validate_identities;
use crate::project_validation::_helpers::python_nodes::{
    validate_check_dependencies, validate_loader_dependencies, validate_python_node_dependencies,
};
use crate::project_validation::_helpers::resource_names::validate_unique_project_resource_names;
use crate::project_validation::_helpers::seeds::validate_declared_seed_files;
use crate::project_validation::models::{
    ModelFact, NamedPath, NodeFact, NodeKind, ProjectFacts, SourceFileFact, ValidationFailure,
};
use sqlbuild_model_config::path_defaults::main::matched_path_default_keys::matched_path_default_keys;

const DLT_LOADER_KIND: &str = "dlt";
const MODELS_PREFIX: &str = "models/";
const CURRENT_DIRECTORY: &str = ".";
const KNOWN_FOLDER_LIMIT: usize = 5;
const RESERVED_MODEL_NAMES: [&str; 1] = ["_chain_"];

/// Validate cross-file conflicts in Python's order; the first conflict is reported.
pub fn validate_project_inputs(facts: &ProjectFacts) -> Result<(), ValidationFailure> {
    validate_identities(facts)?;
    unique_model_file_names(&facts.models)?;
    unique_named(&facts.scenarios, |name, existing, path| {
        format!("Duplicate scenario file name found for '{name}' in {existing} and {path}")
    })?;
    unique_source_names(&facts.sources)?;
    let loaders: Vec<&NodeFact> = nodes_of(facts, NodeKind::Loader);
    unique_named(
        &loaders
            .iter()
            .map(|node| node_path(node))
            .collect::<Vec<_>>(),
        |name, existing, path| {
            format!("Duplicate source loader found for '{name}' in {existing} and {path}")
        },
    )?;
    unique_named(
        &facts.nodes.iter().map(node_path).collect::<Vec<_>>(),
        |name, existing, path| {
            format!(
                "Duplicate Python node found for '{name}' in {existing} and {path}; loader, \
                 task, asset, and check names must be globally unique"
            )
        },
    )?;
    source_loader_name_collisions(&facts.sources, &loaders)?;
    validate_loader_dependencies(&facts.nodes)?;
    validate_python_node_dependencies(&facts.nodes)?;
    validate_check_dependencies(&facts.nodes)?;
    source_loader_references(&facts.sources, &loaders)?;
    terminal_loader_config_ownership(&facts.sources, &loaders)?;
    let schema_models: Vec<NamedPath> = facts
        .schemas
        .iter()
        .flat_map(|schema| {
            schema.model_names.iter().map(|name| NamedPath {
                name: name.clone(),
                path: schema.path.clone(),
            })
        })
        .collect();
    unique_named(&schema_models, |name, existing, path| {
        format!(
            "Duplicate schema.yml model declaration found for '{name}' in {existing} and {path}"
        )
    })?;
    unique_named(&schema_seeds(facts), |name, existing, path| {
        format!("Duplicate seed declaration found for '{name}' in {existing} and {path}")
    })?;
    unique_logical_relation_names(facts)?;
    validate_declared_seed_files(facts)?;
    validate_unique_project_resource_names(facts)?;
    path_defaults_match_models(facts)?;
    Ok(())
}

pub(crate) fn conflict(message: String) -> ValidationFailure {
    DiscoveryFailure::new(FailureKind::Conflict, message).into()
}

pub(crate) fn schema_seeds(facts: &ProjectFacts) -> Vec<NamedPath> {
    facts
        .schemas
        .iter()
        .flat_map(|schema| {
            schema.seeds.iter().map(|seed| NamedPath {
                name: seed.name.clone(),
                path: schema.path.clone(),
            })
        })
        .collect()
}

fn nodes_of(facts: &ProjectFacts, kind: NodeKind) -> Vec<&NodeFact> {
    facts
        .nodes
        .iter()
        .filter(|node| node.kind == kind)
        .collect()
}

fn node_path(node: &NodeFact) -> NamedPath {
    NamedPath {
        name: node.name.clone(),
        path: node.path.clone(),
    }
}

/// Reject the second of two entries with the same name.
fn unique_named(
    entries: &[impl std::borrow::Borrow<NamedPath>],
    message: impl Fn(&str, &str, &str) -> String,
) -> Result<(), ValidationFailure> {
    let mut seen: HashMap<&str, &str> = HashMap::new();
    for entry in entries {
        let entry: &NamedPath = entry.borrow();
        if let Some(existing) = seen.get(entry.name.as_str()) {
            return Err(conflict(message(&entry.name, existing, &entry.path)));
        }
        seen.insert(&entry.name, &entry.path);
    }
    Ok(())
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

fn unique_source_names(sources: &[SourceFileFact]) -> Result<(), ValidationFailure> {
    let entries: Vec<NamedPath> = sources
        .iter()
        .flat_map(|file| {
            file.entries.iter().map(|entry| NamedPath {
                name: entry.name.clone(),
                path: file.path.clone(),
            })
        })
        .collect();
    unique_named(&entries, |name, existing, path| {
        format!("Duplicate source declaration found for '{name}' in {existing} and {path}")
    })
}

fn source_loader_name_collisions(
    sources: &[SourceFileFact],
    loaders: &[&NodeFact],
) -> Result<(), ValidationFailure> {
    let loader_paths: HashMap<&str, &str> = loaders
        .iter()
        .map(|loader| (loader.name.as_str(), loader.path.as_str()))
        .collect();
    for file in sources {
        for entry in &file.entries {
            let Some(loader_path) = loader_paths.get(entry.name.as_str()) else {
                continue;
            };
            if entry.managed && entry.loader.as_deref() == Some(entry.name.as_str()) {
                continue;
            }
            return Err(conflict(format!(
                "Source '{name}' in {path} conflicts with loader '{name}' in {loader_path}; \
                 source and loader names must be globally unique unless the source is managed",
                name = entry.name,
                path = file.path,
            )));
        }
    }
    Ok(())
}

/// Python's `integration_loader_name`.
fn integration_loader_name(kind: &str, source_name: &str) -> String {
    if kind == DLT_LOADER_KIND {
        source_name.to_owned()
    } else {
        format!("{kind}__{source_name}")
    }
}

fn source_loader_references(
    sources: &[SourceFileFact],
    loaders: &[&NodeFact],
) -> Result<(), ValidationFailure> {
    let loader_names: HashSet<&str> = loaders.iter().map(|loader| loader.name.as_str()).collect();
    for file in sources {
        for entry in &file.entries {
            let expected: String = match &entry.integration_loader {
                Some(integration) => integration_loader_name(&integration.kind, &entry.name),
                None => entry.name.clone(),
            };
            if entry.managed && entry.loader.as_deref() != Some(expected.as_str()) {
                return Err(conflict(format!(
                    "Managed source '{}' in {} must use terminal loader '{expected}'",
                    entry.name, file.path
                )));
            }
            if entry.managed && !loader_names.contains(expected.as_str()) {
                return Err(conflict(format!(
                    "Managed source '{}' in {} requires loader '{expected}'",
                    entry.name, file.path
                )));
            }
            match &entry.loader {
                Some(loader) if !loader_names.contains(loader.as_str()) => {
                    return Err(conflict(format!(
                        "Source '{}' in {} references unknown loader '{loader}'",
                        entry.name, file.path
                    )));
                }
                _ => {}
            }
        }
    }
    Ok(())
}

fn terminal_loader_config_ownership(
    sources: &[SourceFileFact],
    loaders: &[&NodeFact],
) -> Result<(), ValidationFailure> {
    let by_name: HashMap<&str, &NodeFact> = loaders
        .iter()
        .map(|loader| (loader.name.as_str(), *loader))
        .collect();
    for file in sources {
        for entry in &file.entries {
            let Some(loader) = &entry.loader else {
                continue;
            };
            let configured: bool = by_name
                .get(loader.as_str())
                .is_some_and(|loader| loader.decorator_config);
            if configured {
                return Err(conflict(format!(
                    "Source '{}' references loader '{loader}', but terminal source loader write \
                     and schema config must be declared in source YAML, not the @loader decorator",
                    entry.name
                )));
            }
        }
    }
    Ok(())
}

fn unique_logical_relation_names(facts: &ProjectFacts) -> Result<(), ValidationFailure> {
    let mut seen: HashMap<String, (&'static str, String)> = HashMap::new();
    for model in &facts.models {
        seen.insert(model.file.name.clone(), ("model", model.file.path.clone()));
    }
    let sources = facts.sources.iter().flat_map(|file| {
        file.entries
            .iter()
            .map(move |entry| ("source", entry.name.clone(), file.path.clone()))
    });
    let seeds = schema_seeds(facts)
        .into_iter()
        .map(|seed| ("seed", seed.name, seed.path));
    for (kind, name, path) in sources.chain(seeds) {
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

fn path_defaults_match_models(facts: &ProjectFacts) -> Result<(), ValidationFailure> {
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
