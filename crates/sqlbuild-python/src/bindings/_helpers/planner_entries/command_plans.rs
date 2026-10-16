//! Static plans for commands that do not build models, and direct seed identity reads.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use crate::bindings::_helpers::planner_entries::models::RelationsRequest;
use crate::bindings::_helpers::planner_entries::plan_output::{
    function_entry, selected_test_entries, test_selected,
};
use crate::bindings::_helpers::planner_entries::relations::planner_relations_context;
use crate::bindings::_helpers::planner_entries::values::{
    boolean, native, none, planner_model, planner_type,
};
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyList, PyListMethods, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::fingerprint_storage::constants::NODE_TYPE_SEED;
use sqlbuild_core::constants::FINGERPRINT_TABLE_NAME;
use std::collections::{BTreeMap, BTreeSet};

/// Optional fields of a static command plan; absent ones take `PlanOutput` defaults.
#[derive(Default)]
struct StaticPlanParts<'py> {
    execution_order: Option<Bound<'py, PyAny>>,
    fields: Vec<(&'static str, Bound<'py, PyAny>)>,
}

fn base_plan_output<'py>(
    project: &Bound<'py, PyAny>,
    scope: &Bound<'py, PyAny>,
    relations: &Bound<'py, PyAny>,
    parts: StaticPlanParts<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = project.py();
    let selected_keys = scope.getattr("selected_keys")?;
    let execution_order = match parts.execution_order {
        Some(order) => order,
        None => {
            let mut order: Vec<Bound<'py, PyAny>> = Vec::new();
            for key in scope.getattr("execution_order")?.try_iter()? {
                let key = key?;
                if selected_keys.contains(&key)? {
                    order.push(key);
                }
            }
            PyTuple::new(py, order)?.into_any()
        }
    };
    let mut fields = vec![("execution_order", execution_order)];
    fields.extend(parts.fields);
    fields.extend([
        ("selected_keys", selected_keys),
        ("upstream_deps", scope.getattr("upstream_deps")?),
        ("downstream_deps", scope.getattr("downstream_deps")?),
        ("model_locations", relations.getattr("model_locations")?),
        ("seed_locations", relations.getattr("seed_locations")?),
        (
            "function_locations",
            relations.getattr("function_locations")?,
        ),
        ("source_map", relations.getattr("source_map")?),
        ("source_read_map", relations.getattr("source_read_map")?),
        (
            "python_source_read_map",
            relations.getattr("python_source_read_map")?,
        ),
        ("hook_functions", project.getattr("hook_functions")?),
        (
            "enforce_explicit_references",
            project.getattr("enforce_explicit_references")?,
        ),
    ]);
    planner_model(py, RecordId::PlanOutput, &fields)
}

/// Resolve command selection through the canonical build selector phase.
#[pyfunction]
#[pyo3(signature = (*, project, selection, auto_load_sources = false))]
fn resolve_static_command_scope<'py>(
    project: &Bound<'py, PyAny>,
    selection: &Bound<'py, PyAny>,
    auto_load_sources: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let py = project.py();
    native(
        py,
        NativeAttr::ResolvePlannerScopes,
        &[
            ("project", project.clone()),
            ("selection", selection.clone()),
            (
                "policies",
                planner_model(
                    py,
                    RecordId::PlannerPolicies,
                    &[("auto_load_sources", boolean(py, auto_load_sources)?)],
                )?,
            ),
        ],
    )?
    .getattr("selected_scope")
}

/// Resolve canonical locations and source routing without warehouse inventory.
#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn resolve_static_relation_context<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "resolve_static_relation_context",
        kwargs,
        (
            &["project", "adapter", "scope"],
            &[
                "deferral",
                "project_config",
                "local_config",
                "relation_keys",
            ],
        ),
    )?;
    planner_relations_context(RelationsRequest {
        project: args.value("project")?,
        adapter: args.value("adapter")?,
        connection: none(py),
        scope: args.value("scope")?,
        deferral: args.value("deferral")?,
        project_config: args.value("project_config")?,
        local_config: args.value("local_config")?,
        known_source_columns: PyDict::new(py).into_any(),
        relation_keys: args.value("relation_keys")?,
    })
}

/// Project selected audits from canonical static state.
#[pyfunction]
#[pyo3(signature = (*, project, adapter, scope, relations))]
fn build_audit_command_plan<'py>(
    project: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
    scope: &Bound<'py, PyAny>,
    relations: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = project.py();
    let materializations = PyDict::new(py);
    for model in project.getattr("models")?.try_iter()? {
        let model = model?;
        materializations.set_item(
            model_reads::name_object(&model)?,
            native(
                py,
                NativeAttr::GetMaterializationType,
                &[("model", model.clone())],
            )?
            .getattr("value")?,
        )?;
    }
    let audits = native(
        py,
        NativeAttr::BuildSelectedAuditEntries,
        &[
            ("project", project.clone()),
            ("adapter", adapter.clone()),
            ("scope", scope.clone()),
            ("relations", relations.clone()),
            ("model_materializations", materializations.into_any()),
        ],
    )?;
    base_plan_output(
        project,
        scope,
        relations,
        StaticPlanParts {
            execution_order: None,
            fields: vec![(
                "audit_entries",
                PyTuple::new(py, audits.try_iter()?.collect::<PyResult<Vec<_>>>()?)?.into_any(),
            )],
        },
    )
}

/// Project selected SQL tests from canonical static state.
#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn build_test_command_plan<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "build_test_command_plan",
        kwargs,
        (
            &["project", "adapter", "scope", "relations"],
            &["case_name"],
        ),
    )?;
    let project = args.value("project")?;
    let adapter = args.value("adapter")?;
    let scope = args.value("scope")?;
    let relations = args.value("relations")?;
    let selected_keys = scope.getattr("selected_keys")?;
    let selection = scope.getattr("sql_test_selection")?;
    let selected = selected_test_entries(
        (&project, &adapter),
        &selected_keys,
        &selection,
        &args.value("case_name")?,
    )?;
    let (entries, warnings) = (selected.entries, selected.warnings);
    let mut case_names: BTreeSet<String> = BTreeSet::new();
    for test in project.getattr("sql_tests")?.try_iter()? {
        let test = test?;
        let case_name = test.getattr("case_name")?;
        if !case_name.is_none() && test_selected(&test, &selected_keys, &selection)? {
            case_names.insert(case_name.extract()?);
        }
    }
    let mut test_keys: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut function_keys: Vec<Bound<'py, PyAny>> = Vec::new();
    for entry in &entries {
        test_keys.push(entry.getattr("key")?);
        for key in entry.getattr("function_deps")?.try_iter()? {
            function_keys.push(key?);
        }
    }
    let function_keys = PyFrozenSet::new(py, function_keys)?;
    let mut functions: Vec<Bound<'py, PyAny>> = Vec::new();
    for function in project.getattr("functions")?.try_iter()? {
        let function = function?;
        if !function_keys.contains(function.getattr("key")?)? {
            continue;
        }
        let fingerprint_sql = native(
            py,
            NativeAttr::BuildCompiledFunctionFingerprintSql,
            &[("function", function.clone())],
        )?;
        functions.push(function_entry(
            &function,
            &adapter,
            &relations,
            (
                fingerprint_sql,
                none(py),
                planner_type(py, RecordId::PlanReason, "NO_CHANGE")?,
            ),
        )?);
    }
    let scoped_keys = selected_keys.call_method1("__or__", (PyFrozenSet::new(py, test_keys)?,))?;
    let mut order: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in scope.getattr("execution_order")?.try_iter()? {
        let key = key?;
        if scoped_keys.contains(&key)? {
            order.push(key);
        }
    }
    base_plan_output(
        &project,
        &scope,
        &relations,
        StaticPlanParts {
            execution_order: Some(PyTuple::new(py, order)?.into_any()),
            fields: vec![
                ("test_entries", PyTuple::new(py, entries)?.into_any()),
                (
                    "available_test_case_names",
                    PyTuple::new(py, case_names)?.into_any(),
                ),
                ("function_entries", PyTuple::new(py, functions)?.into_any()),
                ("warnings", PyTuple::new(py, warnings)?.into_any()),
            ],
        },
    )
}

/// Project selected direct seed work and canonical identities.
#[pyfunction]
#[pyo3(signature = (*, project, scope, relations, fingerprints = None))]
fn build_seed_command_plan<'py>(
    project: &Bound<'py, PyAny>,
    scope: &Bound<'py, PyAny>,
    relations: &Bound<'py, PyAny>,
    fingerprints: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = project.py();
    let existing = match fingerprints {
        Some(fingerprints) if fingerprints.is_truthy()? => fingerprints,
        _ => PyDict::new(py).into_any(),
    };
    let selected_keys = scope.getattr("selected_keys")?;
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    for seed in project.getattr("seeds")?.try_iter()? {
        let seed = seed?;
        if !selected_keys.contains(seed.getattr("key")?)? {
            continue;
        }
        let identity = native(py, NativeAttr::BuildSeedIdentity, &[("seed", seed.clone())])?;
        let (version_hash, metadata_json) = (identity.get_item(0)?, identity.get_item(1)?);
        let previous = existing.call_method1("get", (seed.getattr("name")?,))?;
        let reason = if previous.is_none() {
            "FIRST_RUN"
        } else if previous.getattr("version_hash")?.ne(&version_hash)? {
            "CONFIG_CHANGED"
        } else {
            "NO_CHANGE"
        };
        entries.push(planner_model(
            py,
            RecordId::SeedPlanEntry,
            &[
                ("key", seed.getattr("key")?),
                ("name", seed.getattr("name")?),
                ("destination", seed.getattr("destination")?),
                (
                    "file_path",
                    seed.getattr("seed_file")?.getattr("file_path")?,
                ),
                (
                    "columns",
                    native(
                        py,
                        NativeAttr::ExtractSeedColumns,
                        &[("seed", seed.clone())],
                    )?,
                ),
                (
                    "csv_settings",
                    seed.getattr("schema_entry")?.getattr("csv_settings")?,
                ),
                ("fingerprint_definition", metadata_json.clone()),
                ("fingerprint_version_hash", version_hash),
                ("fingerprint_metadata_json", metadata_json),
                ("reason", planner_type(py, RecordId::PlanReason, reason)?),
            ],
        )?);
    }
    base_plan_output(
        project,
        scope,
        relations,
        StaticPlanParts {
            execution_order: None,
            fields: vec![("seed_entries", PyTuple::new(py, entries)?.into_any())],
        },
    )
}

/// Project static relation data for Python checks.
#[pyfunction]
#[pyo3(signature = (*, project, scope, relations))]
fn build_relation_command_plan<'py>(
    project: &Bound<'py, PyAny>,
    scope: &Bound<'py, PyAny>,
    relations: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    base_plan_output(project, scope, relations, StaticPlanParts::default())
}

/// A schema target's sort key: the database with `None` first as an empty name, then the schema.
type Target = (Option<String>, String);

/// Read only fingerprint state required by selected direct seeds.
#[pyfunction]
#[pyo3(signature = (*, adapter, connection, seeds))]
fn read_selected_seed_fingerprints<'py>(
    adapter: &Bound<'py, PyAny>,
    connection: &Bound<'py, PyAny>,
    seeds: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py = adapter.py();
    let table_name: &str = FINGERPRINT_TABLE_NAME;
    let mut names_by_target: BTreeMap<(String, String), (Target, BTreeSet<String>)> =
        BTreeMap::new();
    for seed in seeds.try_iter()? {
        let seed = seed?;
        let destination = seed.getattr("destination")?;
        let schema = destination.getattr("schema")?;
        if schema.is_none() {
            continue;
        }
        let database: Option<String> = destination.getattr("database")?.extract()?;
        let schema: String = schema.extract()?;
        names_by_target
            .entry((database.clone().unwrap_or_default(), schema.clone()))
            .or_insert_with(|| ((database, schema), BTreeSet::new()))
            .1
            .insert(seed.getattr("name")?.extract()?);
    }
    let fingerprints = PyDict::new(py);
    let mut relations_by_target: Vec<Bound<'py, PyAny>> = Vec::new();
    for ((database, schema), _) in names_by_target.values() {
        let names = PyTuple::new(py, [table_name])?;
        let schemas = PyTuple::new(py, [schema.as_str()])?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("connection", connection)?;
        kwargs.set_item("database", database)?;
        kwargs.set_item("schemas", schemas)?;
        kwargs.set_item("names", names)?;
        relations_by_target.push(adapter.getattr("list_relations")?.call((), Some(&kwargs))?);
    }
    for (((database, schema), names), relations) in
        names_by_target.values().zip(relations_by_target)
    {
        let mut table_exists = false;
        for relation in relations.try_iter()? {
            let name: String = relation?.getattr("name")?.extract()?;
            if name.to_lowercase() == table_name.to_lowercase() {
                table_exists = true;
                break;
            }
        }
        let node_names = PyTuple::new(py, names.iter())?;
        let latest = native(
            py,
            NativeAttr::ReadLatestFingerprints,
            &[
                ("connection", connection.clone()),
                ("execute", adapter.getattr("execute")?),
                ("table_exists", boolean(py, table_exists)?),
                (
                    "database",
                    database
                        .as_deref()
                        .map_or_else(|| none(py), |name| PyString::new(py, name).into_any()),
                ),
                ("schema", PyString::new(py, schema).into_any()),
                (
                    "render_qualified_name",
                    adapter.getattr("render_qualified_name")?,
                ),
                (
                    "render_read_latest_sql",
                    adapter.getattr("render_read_latest_fingerprints_sql")?,
                ),
                ("node_names", node_names.into_any()),
            ],
        )?;
        let items = PyList::new(
            py,
            latest
                .getattr("fingerprints")?
                .call_method0("items")?
                .try_iter()?
                .collect::<PyResult<Vec<_>>>()?,
        )?;
        for item in items.iter() {
            let (name, fingerprint) = (item.get_item(0)?, item.get_item(1)?);
            if fingerprint.getattr("node_type")?.eq(NODE_TYPE_SEED)?
                && names.contains(&name.extract::<String>()?)
            {
                fingerprints.set_item(name, fingerprint)?;
            }
        }
    }
    Ok(fingerprints)
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resolve_static_command_scope, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_static_relation_context, module)?)?;
    module.add_function(wrap_pyfunction!(build_audit_command_plan, module)?)?;
    module.add_function(wrap_pyfunction!(build_test_command_plan, module)?)?;
    module.add_function(wrap_pyfunction!(build_seed_command_plan, module)?)?;
    module.add_function(wrap_pyfunction!(build_relation_command_plan, module)?)?;
    module.add_function(wrap_pyfunction!(read_selected_seed_fingerprints, module)?)
}
