//! The definition snapshot of a compiled project: one fingerprint per node and its declarations.

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyStringMethods};
use serde_json::Value;
use sqlbuild_analysis::definition_changes::constants::{
    AUDITS_ASPECT, COLUMNS_ASPECT, CONFIG_ASPECT, DEFINITION_ASPECT, DEFINITION_SNAPSHOT_FORMAT,
    FILE_ASPECT, MACRO_KIND, MATERIALIZATION_KIND, MODEL_KIND, PYTHON_NODE_KINDS, SCENARIO_KIND,
    SEED_KIND, SETTINGS_KIND, SNAPSHOTS_ASPECT, SOURCE_KIND, SQL_ASPECT, TEST_FILE_KIND,
    VARS_ASPECT,
};
use sqlbuild_analysis::definition_changes::main::definition_digest::definition_digest;
use sqlbuild_analysis::definition_changes::main::node_key::node_key;
use sqlbuild_analysis::definition_changes::main::sql_definition_digest::sql_definition_digest;
use sqlbuild_analysis::definition_changes::models::{DefinitionSnapshot, NodeDefinition};

use crate::bindings::_helpers::change_selection::fingerprints::{
    Fingerprinting, directory_digest, file_digest, text_of,
};
use crate::bindings::_helpers::compiled_views::function_reads;
use crate::bindings::_helpers::compiled_views::model_reads;
use crate::bindings::_helpers::compiled_views::project_reads;
use crate::bindings::_helpers::compiled_views::seed_reads;
use crate::bindings::_helpers::compiled_views::source_reads;
use crate::bindings::_helpers::planner_identity::metadata::{function_local_hashes, seed_identity};
use crate::bindings::_helpers::records::fields::field as native_field;

/// Header values that rename rather than redefine a model.
const RENAME_CONFIG_KEYS: [&str; 2] = ["migrate_from", "description"];
const MIGRATE_FROM_KEY: &str = "migrate_from";
const MATERIALIZED_KEY: &str = "materialized";
/// Which header keys were authored, rather than inherited from defaults, does not change a model.
const AUTHORED_KEYS_FIELD: &str = "model_header_keys";
const SOURCE_EXPRESSION_FIELD: &str = "expression";
const SCENARIO_SNAPSHOT_ROOT: [&str; 2] = ["tests", "_scenario_snapshots"];
const SETTINGS_NAME: &str = "project";
/// Settings that tune how a run executes or validates, not what a node computes.
const RUNTIME_SETTINGS: [&str; 9] = [
    "sql_analysis",
    "require_sql_analysis",
    "concurrency",
    "microbatch_concurrency",
    "test_timeout",
    "test_timeout_seconds",
    "scenario_timeout",
    "scenario_timeout_seconds",
    "delta_compile",
];
const PYTHON_SUFFIX: &str = ".py";
/// Discovered Python node collections, in `PYTHON_NODE_KINDS` order.
const PYTHON_NODE_COLLECTIONS: [&str; 4] = [
    "loader_functions",
    "task_functions",
    "asset_functions",
    "check_functions",
];

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

/// The digest of a declaration file: Python with its imports, anything else as normalised SQL.
fn declaration_file_digest(fingerprints: &Fingerprinting, path: &str) -> String {
    if path.ends_with(PYTHON_SUFFIX) {
        return fingerprints.python_module_digest(Path::new(path));
    }
    match std::fs::read_to_string(fingerprints.project_dir.join(path)) {
        Ok(contents) => {
            let mut parts: Vec<String> = vec![sql_definition_digest(&contents)];
            parts.extend(fingerprints.referenced_vars_digest(&contents));
            let borrowed: Vec<&str> = parts.iter().map(String::as_str).collect();
            definition_digest(&borrowed)
        }
        Err(_) => definition_digest(&["missing"]),
    }
}

/// Scope declarations: a macro by its facts and Python imports, any other by its declaration file.
fn declaration_nodes(
    project: &Bound<'_, PyAny>,
    fingerprints: &Fingerprinting,
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
                definition_digest(&[
                    &fingerprints.canonical_digest(&macro_facts, (&[], &[]))?,
                    &declaration_file_digest(fingerprints, &path),
                ]),
                dependencies
                    .iter()
                    .map(|dependency| node_key(MACRO_KIND, dependency))
                    .collect(),
            )
        } else {
            (declaration_file_digest(fingerprints, &path), Vec::new())
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

/// The resolved configuration of a model, defaults and path defaults included, without renames.
fn config_digest(fingerprints: &Fingerprinting, config: &Bound<'_, PyAny>) -> PyResult<String> {
    let mut encoded: Value = fingerprints.canonical(config, &[AUTHORED_KEYS_FIELD])?;
    if let Value::Object(fields) = &mut encoded
        && let Some(Value::Object(values)) = fields.get_mut("values")
    {
        for key in RENAME_CONFIG_KEYS {
            values.remove(key);
        }
    }
    Ok(definition_digest(&[&encoded.to_string()]))
}

/// A model by its SQL before macro expansion, resolved configuration, columns, contract, audits
/// and the variables its file reads.
fn model_node(
    model: &Bound<'_, PyAny>,
    fingerprints: &Fingerprinting,
    uses: &BTreeMap<String, BTreeSet<String>>,
) -> PyResult<(String, NodeDefinition)> {
    let name: String = model_reads::model_name(model)?;
    let config: Bound<'_, PyAny> = model_reads::config(model)?;
    let config_values: Bound<'_, PyAny> = native_field(&config, "values")?;
    let schema: Bound<'_, PyAny> = model_reads::schema_entry(model)?;
    let (columns, audits): (String, String) = if schema.is_none() {
        (definition_digest(&[]), definition_digest(&[]))
    } else {
        let mut column_audits: Vec<Value> =
            vec![fingerprints.canonical(&native_field(&schema, "audits")?, &[])?];
        for column in native_field(&schema, "columns")?.try_iter()? {
            column_audits.push(fingerprints.canonical(&native_field(&column?, "audits")?, &[])?);
        }
        (
            fingerprints.canonical_digest(&schema, (&["name", "tags"], &["audits"]))?,
            definition_digest(&[&Value::Array(column_audits).to_string()]),
        )
    };
    let query_sql: String = native_field(model, "authored_query_sql")?.extract()?;
    let authored_sql: String = native_field(model, "authored_sql")?.extract()?;
    let mut aspects: Vec<(&str, String)> = vec![
        (SQL_ASPECT, sql_definition_digest(&query_sql)),
        (CONFIG_ASPECT, config_digest(fingerprints, &config)?),
        (COLUMNS_ASPECT, columns),
        (AUDITS_ASPECT, audits),
    ];
    if let Some(digest) = fingerprints.referenced_vars_digest(&authored_sql) {
        aspects.push((VARS_ASPECT, digest));
    }
    let mut definition: NodeDefinition = node(MODEL_KIND, &name, aspects);
    let key: String = node_key(MODEL_KIND, &name);
    definition.uses = uses.get(&key).into_iter().flatten().cloned().collect();
    definition.uses.push(node_key(SETTINGS_KIND, SETTINGS_NAME));
    if let Ok(values) = config_values.cast::<PyDict>()
        && let Some(materialized) = values.get_item(MATERIALIZED_KEY)?
        && let Ok(materialized) = materialized.cast::<PyString>()
    {
        definition
            .uses
            .push(node_key(MATERIALIZATION_KIND, materialized.to_str()?));
    }
    definition.migrate_from = migrate_from(&config_values)?;
    Ok((key, definition))
}

/// A source by its declaration, with an inline expression's formatting ignored.
fn source_node(
    source: &Bound<'_, PyAny>,
    fingerprints: &Fingerprinting,
) -> PyResult<(String, NodeDefinition)> {
    let name: String = source_reads::name(source)?.extract()?;
    let mut encoded: Value = fingerprints.canonical(&source_reads::source_entry(source)?, &[])?;
    if let Value::Object(fields) = &mut encoded
        && let Some(Value::String(expression)) = fields.get(SOURCE_EXPRESSION_FIELD)
    {
        let normalised: String = sql_definition_digest(expression);
        fields.insert(SOURCE_EXPRESSION_FIELD.to_owned(), Value::from(normalised));
    }
    Ok((
        node_key(SOURCE_KIND, &name),
        node(
            SOURCE_KIND,
            &name,
            vec![(
                DEFINITION_ASPECT,
                definition_digest(&[&encoded.to_string()]),
            )],
        ),
    ))
}

/// Loaders, tasks, assets, checks and materializations by their Python modules and imports.
fn python_nodes(
    discovered: &Bound<'_, PyAny>,
    fingerprints: &Fingerprinting,
    nodes: &mut BTreeMap<String, NodeDefinition>,
) -> PyResult<()> {
    let collections = PYTHON_NODE_COLLECTIONS
        .iter()
        .zip(PYTHON_NODE_KINDS)
        .chain([(&"materialization_files", MATERIALIZATION_KIND)]);
    for (collection, kind) in collections {
        let Ok(items) = discovered.getattr(*collection) else {
            continue;
        };
        for item in items.try_iter()? {
            let item: Bound<'_, PyAny> = item?;
            let name: String = item.getattr("name")?.extract()?;
            let path: PathBuf = item.getattr("file_path")?.extract()?;
            nodes.insert(
                node_key(kind, &name),
                node(
                    kind,
                    &name,
                    vec![(DEFINITION_ASPECT, fingerprints.python_module_digest(&path))],
                ),
            );
        }
    }
    Ok(())
}

/// User-defined and table functions by their definitions, Python ones with their imports.
fn function_nodes(
    project: &Bound<'_, PyAny>,
    fingerprints: &Fingerprinting,
    nodes: &mut BTreeMap<String, NodeDefinition>,
) -> PyResult<()> {
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
        let mut digest: String = hash.extract()?;
        let source_file: Bound<'_, PyAny> = function_reads::source_file_path(&function)?;
        if !source_file.is_none() {
            let path: String = text_of(&source_file)?;
            if path.ends_with(PYTHON_SUFFIX) {
                digest = definition_digest(&[
                    &digest,
                    &fingerprints.python_module_digest(Path::new(&path)),
                ]);
            }
        }
        let mut definition: NodeDefinition = node(&kind, &name, vec![(DEFINITION_ASPECT, digest)]);
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
        definition.uses.push(node_key(SETTINGS_KIND, SETTINGS_NAME));
        nodes.insert(node_key(&kind, &name), definition);
    }
    Ok(())
}

/// Each unit test file by its text and the variables it reads.
fn test_file_nodes(
    project: &Bound<'_, PyAny>,
    fingerprints: &Fingerprinting,
    nodes: &mut BTreeMap<String, NodeDefinition>,
) -> PyResult<()> {
    for test in project_reads::sql_tests(project)?.try_iter()? {
        let file: Bound<'_, PyAny> = native_field(&test?, "test_file")?;
        let path: String = text_of(&native_field(&file, "relative_path")?)?;
        let key: String = node_key(TEST_FILE_KIND, &path);
        if nodes.contains_key(&key) {
            continue;
        }
        let contents: String = native_field(&file, "contents")?.extract()?;
        let mut aspects: Vec<(&str, String)> = vec![(
            FILE_ASPECT,
            file_digest(&fingerprints.project_dir.join(&path)),
        )];
        if let Some(digest) = fingerprints.referenced_vars_digest(&contents) {
            aspects.push((VARS_ASPECT, digest));
        }
        nodes.insert(key, node(TEST_FILE_KIND, &path, aspects));
    }
    Ok(())
}

/// Each scenario by its file, captured snapshots and the variables it reads.
fn scenario_nodes(
    project: &Bound<'_, PyAny>,
    fingerprints: &Fingerprinting,
    uses: &BTreeMap<String, BTreeSet<String>>,
    nodes: &mut BTreeMap<String, NodeDefinition>,
) -> PyResult<()> {
    let snapshot_root: PathBuf = SCENARIO_SNAPSHOT_ROOT
        .iter()
        .fold(fingerprints.project_dir.clone(), |path, part| {
            path.join(part)
        });
    for scenario in native_field(project, "sql_scenarios")?.try_iter()? {
        let scenario: Bound<'_, PyAny> = scenario?;
        let name: String = native_field(&scenario, "name")?.extract()?;
        let path: String = text_of(&native_field(
            &native_field(&scenario, "scenario_file")?,
            "relative_path",
        )?)?;
        let file: PathBuf = fingerprints.project_dir.join(&path);
        let mut aspects: Vec<(&str, String)> = vec![(FILE_ASPECT, file_digest(&file))];
        if let Some(digest) = directory_digest(&snapshot_root.join(&name)) {
            aspects.push((SNAPSHOTS_ASPECT, digest));
        }
        let contents: String = std::fs::read_to_string(&file).unwrap_or_default();
        if let Some(digest) = fingerprints.referenced_vars_digest(&contents) {
            aspects.push((VARS_ASPECT, digest));
        }
        let key: String = node_key(SCENARIO_KIND, &name);
        let mut definition: NodeDefinition = node(SCENARIO_KIND, &name, aspects);
        definition.uses = uses.get(&key).into_iter().flatten().cloned().collect();
        nodes.insert(key, definition);
    }
    Ok(())
}

/// The definition snapshot of `project`, discovered as `discovered` under `project_dir`.
pub(crate) fn definition_snapshot(
    project: &Bound<'_, PyAny>,
    discovered: &Bound<'_, PyAny>,
    project_dir: &Path,
) -> PyResult<DefinitionSnapshot> {
    let fingerprints: Fingerprinting = Fingerprinting::new(
        project,
        project_dir,
        &native_field(project, "effective_vars")?,
    )?;
    let uses: BTreeMap<String, BTreeSet<String>> = declaration_uses(project)?;
    let mut nodes: BTreeMap<String, NodeDefinition> = declaration_nodes(project, &fingerprints)?;
    nodes.insert(
        node_key(SETTINGS_KIND, SETTINGS_NAME),
        node(
            SETTINGS_KIND,
            SETTINGS_NAME,
            vec![(
                DEFINITION_ASPECT,
                fingerprints.canonical_digest(
                    &native_field(project, "settings")?,
                    (&RUNTIME_SETTINGS, &[]),
                )?,
            )],
        ),
    );
    for model in project_reads::models(project)?.try_iter()? {
        let (key, definition) = model_node(&model?, &fingerprints, &uses)?;
        nodes.insert(key, definition);
    }
    for source in project_reads::sources(project)?.try_iter()? {
        let (key, definition) = source_node(&source?, &fingerprints)?;
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
    function_nodes(project, &fingerprints, &mut nodes)?;
    python_nodes(discovered, &fingerprints, &mut nodes)?;
    test_file_nodes(project, &fingerprints, &mut nodes)?;
    scenario_nodes(project, &fingerprints, &uses, &mut nodes)?;
    Ok(DefinitionSnapshot {
        format: DEFINITION_SNAPSHOT_FORMAT,
        nodes,
    })
}
