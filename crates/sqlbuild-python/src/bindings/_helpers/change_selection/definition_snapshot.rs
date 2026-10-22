//! The definition snapshot of a compiled project: one fingerprint per node and its declarations.

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{
    PyBool, PyDict, PyDictMethods, PyFloat, PyFrozenSet, PyInt, PyList, PySet, PyString,
    PyStringMethods, PyTuple, PyTypeMethods,
};
use serde_json::{Map, Value};
use sqlbuild_analysis::definition_changes::constants::{
    AUDITS_ASPECT, COLUMNS_ASPECT, CONFIG_ASPECT, DEFINITION_ASPECT, DEFINITION_SNAPSHOT_FORMAT,
    FILE_ASPECT, MACRO_KIND, MODEL_KIND, SCENARIO_KIND, SEED_KIND, SNAPSHOTS_ASPECT, SQL_ASPECT,
    TEST_FILE_KIND,
};
use sqlbuild_analysis::definition_changes::main::definition_digest::definition_digest;
use sqlbuild_analysis::definition_changes::main::node_key::node_key;
use sqlbuild_analysis::definition_changes::main::sql_definition_digest::sql_definition_digest;
use sqlbuild_analysis::definition_changes::models::{DefinitionSnapshot, NodeDefinition};

use crate::bindings::_helpers::compiled_views::function_reads;
use crate::bindings::_helpers::compiled_views::model_reads;
use crate::bindings::_helpers::compiled_views::project_reads;
use crate::bindings::_helpers::compiled_views::seed_reads;
use crate::bindings::_helpers::planner_identity::metadata::{function_local_hashes, seed_identity};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::models::NativeRecord;

/// Fields that document a definition without changing what it does.
const DOCUMENTATION_FIELDS: [&str; 3] = ["description", "location", "meta"];
/// Header values that rename rather than redefine a model.
const RENAME_CONFIG_KEYS: [&str; 2] = ["migrate_from", "description"];
const MIGRATE_FROM_KEY: &str = "migrate_from";
const SCENARIO_SNAPSHOT_ROOT: [&str; 2] = ["tests", "_scenario_snapshots"];

/// A stable JSON form of a Python value, without documentation fields of records.
fn canonical(value: &Bound<'_, PyAny>, skipped: &[&str]) -> PyResult<Value> {
    if value.is_none() {
        return Ok(Value::Null);
    }
    if let Ok(cell) = value.cast::<NativeRecord>() {
        let record: &NativeRecord = cell.get();
        let mut fields: Map<String, Value> = Map::new();
        fields.insert("record".to_owned(), Value::from(record.spec.name));
        for (spec, item) in record.spec.fields.iter().zip(&record.values) {
            if DOCUMENTATION_FIELDS.contains(&spec.name) || skipped.contains(&spec.name) {
                continue;
            }
            fields.insert(
                spec.name.to_owned(),
                canonical(item.bind(value.py()), skipped)?,
            );
        }
        return Ok(Value::Object(fields));
    }
    if value.is_instance_of::<PyBool>() {
        return Ok(Value::from(value.extract::<bool>()?));
    }
    if value.is_instance_of::<PyString>() {
        return Ok(Value::from(value.extract::<String>()?));
    }
    if value.is_instance_of::<PyInt>() || value.is_instance_of::<PyFloat>() {
        return Ok(Value::from(value.repr()?.to_string()));
    }
    if value.is_instance_of::<PyTuple>() || value.is_instance_of::<PyList>() {
        let items: Vec<Value> = value
            .try_iter()?
            .map(|item| canonical(&item?, skipped))
            .collect::<PyResult<_>>()?;
        return Ok(Value::Array(items));
    }
    if value.is_instance_of::<PySet>() || value.is_instance_of::<PyFrozenSet>() {
        let mut items: Vec<String> = value
            .try_iter()?
            .map(|item| Ok(canonical(&item?, skipped)?.to_string()))
            .collect::<PyResult<_>>()?;
        items.sort();
        return Ok(Value::from(items));
    }
    if let Ok(mapping) = value.cast::<PyDict>() {
        let mut entries: BTreeMap<String, Value> = BTreeMap::new();
        for (key, item) in mapping.iter() {
            entries.insert(key.str()?.to_string(), canonical(&item, skipped)?);
        }
        return Ok(Value::Object(entries.into_iter().collect()));
    }
    let text: String = value.repr()?.to_string();
    if text.contains(" at 0x") {
        return Ok(Value::from(value.get_type().name()?.to_string()));
    }
    Ok(Value::from(text))
}

/// The digest of `value`'s canonical form, without the top-level record fields `top_skipped`.
fn canonical_digest(
    value: &Bound<'_, PyAny>,
    (top_skipped, skipped): (&[&str], &[&str]),
) -> PyResult<String> {
    let mut encoded: Value = canonical(value, skipped)?;
    if let Value::Object(fields) = &mut encoded {
        for field in top_skipped {
            fields.remove(*field);
        }
    }
    Ok(definition_digest(&[&encoded.to_string()]))
}

fn text_of(value: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(value.str()?.to_string().replace('\\', "/"))
}

/// The digest of a file's bytes, or of its absence.
fn file_digest(path: &Path) -> String {
    match std::fs::read(path) {
        Ok(bytes) => definition_digest(&[&String::from_utf8_lossy(&bytes)]),
        Err(_) => definition_digest(&["missing"]),
    }
}

/// The digest of every file below `directory`, by relative path, or `None` when it is absent.
fn directory_digest(directory: &Path) -> Option<String> {
    let mut files: Vec<(String, String)> = Vec::new();
    let mut pending: Vec<PathBuf> = vec![directory.to_path_buf()];
    while let Some(next) = pending.pop() {
        let entries: std::fs::ReadDir = match std::fs::read_dir(&next) {
            Ok(entries) => entries,
            Err(_) => return None,
        };
        for entry in entries.flatten() {
            let path: PathBuf = entry.path();
            if path.is_dir() {
                pending.push(path);
            } else {
                let relative: String = path
                    .strip_prefix(directory)
                    .unwrap_or(&path)
                    .to_string_lossy()
                    .replace('\\', "/");
                files.push((relative, file_digest(&path)));
            }
        }
    }
    files.sort();
    let parts: Vec<&str> = files
        .iter()
        .flat_map(|(path, digest)| [path.as_str(), digest.as_str()])
        .collect();
    Some(definition_digest(&parts))
}

fn node(kind: &str, name: &str, aspects: Vec<(&str, String)>) -> NodeDefinition {
    NodeDefinition {
        kind: kind.to_owned(),
        name: name.to_owned(),
        aspects: aspects
            .into_iter()
            .map(|(aspect, digest)| (aspect.to_owned(), digest))
            .collect(),
        uses: Vec::new(),
        migrate_from: Vec::new(),
    }
}

/// The node key of a scope declaration identity: `kind:name`, with `@owner` for owned ones.
pub(crate) fn declaration_key(identity: &Bound<'_, PyAny>) -> PyResult<String> {
    let kind: String = text_of(&native_field(&native_field(identity, "kind")?, "value")?)?;
    let name: String = native_field(identity, "name")?.extract()?;
    let owner: Option<String> = native_field(identity, "owner")?.extract()?;
    Ok(match owner {
        Some(owner) => node_key(&kind, &format!("{name}@{owner}")),
        None => node_key(&kind, &name),
    })
}

/// `kind:name` of a usage consumer.
fn consumer_key(consumer: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(node_key(
        &text_of(&native_field(&native_field(consumer, "kind")?, "value")?)?,
        &native_field(consumer, "name")?.extract::<String>()?,
    ))
}

/// Declaration keys each consumer uses, by consumer key, from the project's scope index.
pub(crate) fn declaration_uses(
    project: &Bound<'_, PyAny>,
) -> PyResult<BTreeMap<String, BTreeSet<String>>> {
    let mut uses: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let index: Bound<'_, PyAny> = native_field(project, "scope_index")?;
    if index.is_none() {
        return Ok(uses);
    }
    for usage in native_field(&index, "usages")?.try_iter()? {
        let usage: Bound<'_, PyAny> = usage?;
        uses.entry(consumer_key(&native_field(&usage, "consumer")?)?)
            .or_default()
            .insert(declaration_key(&native_field(&usage, "declaration")?)?);
    }
    Ok(uses)
}

/// Scope declarations: a macro by its module source, any other by its normalised declaration file.
fn declaration_nodes(
    project: &Bound<'_, PyAny>,
    project_dir: &Path,
) -> PyResult<BTreeMap<String, NodeDefinition>> {
    let mut nodes: BTreeMap<String, NodeDefinition> = BTreeMap::new();
    let index: Bound<'_, PyAny> = native_field(project, "scope_index")?;
    if index.is_none() {
        return Ok(nodes);
    }
    for declaration in native_field(&index, "declarations")?.try_iter()? {
        let declaration: Bound<'_, PyAny> = declaration?;
        let identity: Bound<'_, PyAny> = native_field(&declaration, "identity")?;
        let kind: String = text_of(&native_field(&native_field(&identity, "kind")?, "value")?)?;
        let name: String = native_field(&identity, "name")?.extract()?;
        let path: String = native_field(&declaration, "path")?.extract()?;
        let macro_facts: Bound<'_, PyAny> = native_field(&declaration, "macro")?;
        let (digest, uses): (String, Vec<String>) = if kind == MACRO_KIND {
            if macro_facts.is_none() {
                continue;
            }
            let dependencies: Vec<String> =
                native_field(&macro_facts, "dependencies")?.extract()?;
            (
                canonical_digest(&macro_facts, (&[], &[]))?,
                dependencies
                    .iter()
                    .map(|dependency| node_key(MACRO_KIND, dependency))
                    .collect(),
            )
        } else {
            let digest: String = match std::fs::read_to_string(project_dir.join(&path)) {
                Ok(contents) => sql_definition_digest(&contents),
                Err(_) => definition_digest(&["missing"]),
            };
            (digest, Vec::new())
        };
        let mut definition: NodeDefinition = node(&kind, &name, vec![(DEFINITION_ASPECT, digest)]);
        definition.uses = uses;
        nodes.insert(declaration_key(&identity)?, definition);
    }
    Ok(nodes)
}

fn migrate_from(config_values: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    let Ok(values) = config_values.cast::<PyDict>() else {
        return Ok(Vec::new());
    };
    let Some(value) = values.get_item(MIGRATE_FROM_KEY)? else {
        return Ok(Vec::new());
    };
    if value.is_instance_of::<PyString>() {
        return Ok(vec![value.extract()?]);
    }
    value.try_iter()?.map(|name| name?.extract()).collect()
}

/// A model by its SQL before macro expansion, header configuration, columns, contract and audits.
fn model_node(
    model: &Bound<'_, PyAny>,
    uses: &BTreeMap<String, BTreeSet<String>>,
) -> PyResult<(String, NodeDefinition)> {
    let name: String = model_reads::model_name(model)?;
    let config_values: Bound<'_, PyAny> = native_field(&model_reads::config(model)?, "values")?;
    let config: Bound<'_, PyDict> = PyDict::new(model.py());
    if let Ok(values) = config_values.cast::<PyDict>() {
        for (key, value) in values.iter() {
            if !RENAME_CONFIG_KEYS.contains(&key.str()?.to_str()?) {
                config.set_item(key, value)?;
            }
        }
    }
    let schema: Bound<'_, PyAny> = model_reads::schema_entry(model)?;
    let (columns, audits): (String, String) = if schema.is_none() {
        (definition_digest(&[]), definition_digest(&[]))
    } else {
        let mut column_audits: Vec<Value> =
            vec![canonical(&native_field(&schema, "audits")?, &[])?];
        for column in native_field(&schema, "columns")?.try_iter()? {
            column_audits.push(canonical(&native_field(&column?, "audits")?, &[])?);
        }
        (
            canonical_digest(&schema, (&["name", "tags"], &["audits"]))?,
            definition_digest(&[&Value::Array(column_audits).to_string()]),
        )
    };
    let query_sql: String = native_field(model, "authored_query_sql")?.extract()?;
    let mut definition: NodeDefinition = node(
        MODEL_KIND,
        &name,
        vec![
            (SQL_ASPECT, sql_definition_digest(&query_sql)),
            (
                CONFIG_ASPECT,
                canonical_digest(config.as_any(), (&[], &[]))?,
            ),
            (COLUMNS_ASPECT, columns),
            (AUDITS_ASPECT, audits),
        ],
    );
    let key: String = node_key(MODEL_KIND, &name);
    definition.uses = uses.get(&key).into_iter().flatten().cloned().collect();
    definition.migrate_from = migrate_from(&config_values)?;
    Ok((key, definition))
}

/// The definition snapshot of `project`, whose authored files live under `project_dir`.
pub(crate) fn definition_snapshot(
    project: &Bound<'_, PyAny>,
    project_dir: &Path,
) -> PyResult<DefinitionSnapshot> {
    let uses: BTreeMap<String, BTreeSet<String>> = declaration_uses(project)?;
    let mut nodes: BTreeMap<String, NodeDefinition> = declaration_nodes(project, project_dir)?;
    for model in project_reads::models(project)?.try_iter()? {
        let (key, definition) = model_node(&model?, &uses)?;
        nodes.insert(key, definition);
    }
    for seed in project_reads::seeds(project)?.try_iter()? {
        let seed: Bound<'_, PyAny> = seed?;
        let name: String = seed_reads::name(&seed)?.extract()?;
        let (version_hash, _) = seed_identity(&seed)?;
        nodes.insert(
            node_key(SEED_KIND, &name),
            node(SEED_KIND, &name, vec![(DEFINITION_ASPECT, version_hash)]),
        );
    }
    let functions: Bound<'_, PyAny> = project_reads::functions(project)?;
    let hashes: Bound<'_, PyDict> = function_local_hashes(&functions, None)?;
    for function in functions.try_iter()? {
        let function: Bound<'_, PyAny> = function?;
        let key: Bound<'_, PyAny> = function_reads::key(&function)?;
        let kind: String = text_of(&native_field(
            &native_field(&key, "resource_type")?,
            "value",
        )?)?;
        let name: String = function_reads::name(&function)?.extract()?;
        let Some(hash) = hashes.get_item(&name)? else {
            continue;
        };
        let mut definition: NodeDefinition =
            node(&kind, &name, vec![(DEFINITION_ASPECT, hash.extract()?)]);
        for dependency in function_reads::deps(&function)?.try_iter()? {
            let dependency: Bound<'_, PyAny> = dependency?;
            definition.uses.push(node_key(
                &text_of(&native_field(
                    &native_field(&dependency, "resource_type")?,
                    "value",
                )?)?,
                &native_field(&dependency, "name")?.extract::<String>()?,
            ));
        }
        nodes.insert(node_key(&kind, &name), definition);
    }
    for test in project_reads::sql_tests(project)?.try_iter()? {
        let file: Bound<'_, PyAny> = native_field(&test?, "test_file")?;
        let path: String = text_of(&native_field(&file, "relative_path")?)?;
        nodes
            .entry(node_key(TEST_FILE_KIND, &path))
            .or_insert_with(|| {
                node(
                    TEST_FILE_KIND,
                    &path,
                    vec![(FILE_ASPECT, file_digest(&project_dir.join(&path)))],
                )
            });
    }
    let snapshot_root: PathBuf = SCENARIO_SNAPSHOT_ROOT
        .iter()
        .fold(project_dir.to_path_buf(), |path, part| path.join(part));
    for scenario in native_field(project, "sql_scenarios")?.try_iter()? {
        let scenario: Bound<'_, PyAny> = scenario?;
        let name: String = native_field(&scenario, "name")?.extract()?;
        let path: String = text_of(&native_field(
            &native_field(&scenario, "scenario_file")?,
            "relative_path",
        )?)?;
        let mut aspects: Vec<(&str, String)> =
            vec![(FILE_ASPECT, file_digest(&project_dir.join(&path)))];
        if let Some(digest) = directory_digest(&snapshot_root.join(&name)) {
            aspects.push((SNAPSHOTS_ASPECT, digest));
        }
        let key: String = node_key(SCENARIO_KIND, &name);
        let mut definition: NodeDefinition = node(SCENARIO_KIND, &name, aspects);
        definition.uses = uses.get(&key).into_iter().flatten().cloned().collect();
        nodes.insert(key, definition);
    }
    Ok(DefinitionSnapshot {
        format: DEFINITION_SNAPSHOT_FORMAT,
        nodes,
    })
}
