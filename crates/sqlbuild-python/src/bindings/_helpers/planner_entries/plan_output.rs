//! `PlanOutput` assembly from planned model entries, seeds, sources, functions, audits and tests.

use crate::bindings::_helpers::boundary::python_calls::KeywordArguments;
use crate::bindings::_helpers::boundary::python_calls::keywords;
use crate::bindings::_helpers::planner_entries::model_entries::scope_overlaps;
use crate::bindings::_helpers::planner_entries::models::PlanOutputInputs;
use crate::bindings::_helpers::planner_entries::values::{
    error_of, native, none, planner_model, planner_type, string,
};
use crate::bindings::_helpers::planner_phases::objects::object;
use crate::bindings::_helpers::planner_resolution::orchestration::resolve_function_sql;
use crate::bindings::_helpers::planner_scope::loaders::upstream_loader_dependency_names;
use crate::bindings::_helpers::planner_scope::sources::build_source_load_entries;
use crate::bindings::_helpers::planner_strategy::audit_entries::build_selected_audit_entries;
use crate::bindings::_helpers::planner_strategy::fixture_context::planning_context;
use crate::bindings::_helpers::planner_strategy::model_entries::extract_seed_columns;
use crate::bindings::_helpers::records::construct::record_class;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::mapping_get;
use crate::bindings::_helpers::records::ids::{ErrorId, RecordId};
use crate::bindings::_helpers::sql_test_glue::models::SqlTestAssembly;
use crate::bindings::_helpers::sql_test_glue::plan_assembly::assemble_sql_test_plans;
use crate::bindings::_helpers::sql_test_glue::plan_driver::sql_test_model_chain_names_by_key;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyList, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

const LOADER_CONSUMER: &str = "loader";
const HOOK_CONSUMER: &str = "hook";
const MATERIALIZATION_CONSUMER: &str = "custom materialization";

fn tuple_of<'py>(py: Python<'py>, items: Vec<Bound<'py, PyAny>>) -> PyResult<Bound<'py, PyAny>> {
    Ok(PyTuple::new(py, items)?.into_any())
}

/// `mapping.get(key)` for an optional mapping.
fn optional_get<'py>(
    mapping: &Bound<'py, PyAny>,
    key: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    if mapping.is_truthy()? {
        return mapping_get(mapping, key);
    }
    Ok(none(mapping.py()))
}

fn optional_get_or<'py>(
    mapping: &Bound<'py, PyAny>,
    key: &Bound<'py, PyAny>,
    default: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let value = optional_get(mapping, key)?;
    if value.is_none() {
        return Ok(string(mapping.py(), default));
    }
    Ok(value)
}

fn by_name<'py>(items: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let lookup = PyDict::new(items.py());
    for item in items.try_iter()? {
        let item = item?;
        lookup.set_item(native_field(&item, "name")?, item)?;
    }
    Ok(lookup)
}

/// The plan reason for one selected seed.
fn seed_plan_reason<'py>(
    seed_name: &Bound<'py, PyAny>,
    expected_version_hash: &Bound<'py, PyAny>,
    snapshot: &Bound<'py, PyAny>,
    seed_plan_reasons: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = seed_name.py();
    let reason = optional_get(seed_plan_reasons, seed_name)?;
    if !reason.is_none() {
        return Ok(reason);
    }
    if !native_field(snapshot, "existing_relations")?.contains(seed_name)? {
        return planner_type(py, RecordId::PlanReason, "FIRST_RUN");
    }
    let fingerprint = native_field(&native_field(snapshot, "fingerprints")?, "seeds")?
        .call_method1("get", (seed_name,))?;
    if fingerprint.is_none() {
        return planner_type(py, RecordId::PlanReason, "FIRST_RUN");
    }
    if !expected_version_hash.is_none()
        && native_field(&fingerprint, "version_hash")?.ne(expected_version_hash)?
    {
        return planner_type(py, RecordId::PlanReason, "CONFIG_CHANGED");
    }
    planner_type(py, RecordId::PlanReason, "NO_CHANGE")
}

fn seed_entries<'py>(
    project: &Bound<'py, PyAny>,
    snapshot: &Bound<'py, PyAny>,
    selected_keys: &Bound<'py, PyAny>,
    extras: &Bound<'py, PyAny>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py = project.py();
    let version_hashes = native_field(extras, "seed_version_hashes")?;
    let metadata_jsons = native_field(extras, "seed_metadata_jsons")?;
    let plan_reasons = native_field(extras, "seed_plan_reasons")?;
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    for seed in native_field(project, "seeds")?.try_iter()? {
        let seed = seed?;
        if !selected_keys.contains(native_field(&seed, "key")?)? {
            continue;
        }
        let name = native_field(&seed, "name")?;
        entries.push(planner_model(
            py,
            RecordId::SeedPlanEntry,
            &[
                ("key", native_field(&seed, "key")?),
                ("name", name.clone()),
                ("destination", native_field(&seed, "destination")?),
                (
                    "file_path",
                    native_field(&native_field(&seed, "seed_file")?, "file_path")?,
                ),
                ("columns", object(py, extract_seed_columns(&seed)?)?),
                (
                    "csv_settings",
                    native_field(&native_field(&seed, "schema_entry")?, "csv_settings")?,
                ),
                (
                    "fingerprint_definition",
                    optional_get_or(&metadata_jsons, &name, "")?,
                ),
                (
                    "fingerprint_version_hash",
                    optional_get_or(&version_hashes, &name, "")?,
                ),
                (
                    "fingerprint_metadata_json",
                    optional_get_or(&metadata_jsons, &name, "{}")?,
                ),
                (
                    "reason",
                    seed_plan_reason(
                        &name,
                        &optional_get(&version_hashes, &name)?,
                        snapshot,
                        &plan_reasons,
                    )?,
                ),
            ],
        )?);
    }
    Ok(entries)
}

fn provider_usages<'py>(
    provider_usages: &Bound<'py, PyAny>,
    consumer_kind: &str,
    consumer_name: &Bound<'py, PyAny>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py = consumer_name.py();
    let mut usages: Vec<Bound<'py, PyAny>> = Vec::new();
    for usage in provider_usages.try_iter()? {
        let usage = usage?;
        usages.push(native(
            py,
            RecordId::PlanProviderUsage,
            &[
                ("provider_name", native_field(&usage, "provider_name")?),
                ("consumer_kind", string(py, consumer_kind)),
                ("consumer_name", consumer_name.clone()),
                ("parameter_name", native_field(&usage, "parameter_name")?),
                (
                    "annotation_class_name",
                    native_field(&usage, "annotation_class_name")?,
                ),
                (
                    "annotation_module",
                    native_field(&usage, "annotation_module")?,
                ),
            ],
        )?);
    }
    Ok(usages)
}

fn hook_provider_usages<'py>(
    entry: &Bound<'py, PyAny>,
    hook_by_name: &Bound<'py, PyDict>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py = entry.py();
    let mut usages: Vec<Bound<'py, PyAny>> = Vec::new();
    let python_hook = record_class(py, RecordId::PythonHookEntry)?;
    let mut hooks: Vec<Bound<'py, PyAny>> = Vec::new();
    for field in ["pre_hooks", "post_hooks"] {
        let hook_entry = native_field(entry, field)?;
        if hook_entry.is_none() {
            continue;
        }
        if hook_entry.is_instance_of::<PyList>() || hook_entry.is_instance_of::<PyTuple>() {
            for hook in hook_entry.try_iter()? {
                hooks.push(hook?);
            }
        } else {
            hooks.push(hook_entry);
        }
    }
    for hook in hooks {
        if !hook.is_instance(&python_hook)? {
            continue;
        }
        let Some(discovered) = hook_by_name.get_item(native_field(&hook, "name")?)? else {
            continue;
        };
        usages.extend(provider_usages(
            &native_field(&discovered, "provider_usages")?,
            HOOK_CONSUMER,
            &native_field(&discovered, "name")?,
        )?);
    }
    Ok(usages)
}

/// Provider usages of the planned loaders, hooks and custom materializations, in plan order.
fn plan_provider_usages<'py>(
    project: &Bound<'py, PyAny>,
    model_entries: &Bound<'py, PyAny>,
    source_load_entries: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = project.py();
    let mut usages: Vec<Bound<'py, PyAny>> = Vec::new();
    let loader_by_name = by_name(&native_field(project, "loader_functions")?)?;
    for entry in source_load_entries.try_iter()? {
        let Some(loader) = loader_by_name.get_item(native_field(&entry?, "loader")?)? else {
            continue;
        };
        usages.extend(provider_usages(
            &native_field(&loader, "provider_usages")?,
            LOADER_CONSUMER,
            &native_field(&loader, "name")?,
        )?);
    }
    let hook_by_name = by_name(&native_field(project, "hook_functions")?)?;
    let materialization_by_name = by_name(&native_field(project, "materialization_files")?)?;
    for entry in model_entries.try_iter()? {
        let entry = entry?;
        usages.extend(hook_provider_usages(&entry, &hook_by_name)?);
        let custom = native_field(&entry, "custom_materialization_name")?;
        if custom.is_none() {
            continue;
        }
        let Some(materialization) = materialization_by_name.get_item(custom)? else {
            continue;
        };
        usages.extend(provider_usages(
            &native_field(&materialization, "provider_usages")?,
            MATERIALIZATION_CONSUMER,
            &native_field(&materialization, "name")?,
        )?);
    }
    tuple_of(py, usages)
}

/// Fail when a selected loader depends on an unselected intermediate loader with no target.
fn require_intermediate_loader_targets<'py>(
    project: &Bound<'py, PyAny>,
    snapshot: &Bound<'py, PyAny>,
    source_map: &Bound<'py, PyAny>,
    source_load_entries: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let py = project.py();
    let loader_functions = native_field(project, "loader_functions")?;
    let loader_by_name = by_name(&loader_functions)?;
    let selected_names = PyFrozenSet::new(
        py,
        source_load_entries
            .try_iter()?
            .map(|entry| native_field(&entry?, "name"))
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    let existing = native_field(snapshot, "existing_relations")?;
    for entry in source_load_entries.try_iter()? {
        let source_entry = mapping_get(source_map, native_field(&entry?, "name")?)?;
        if source_entry.is_none() || native_field(&source_entry, "loader")?.is_none() {
            continue;
        }
        let Some(loader_function) =
            loader_by_name.get_item(native_field(&source_entry, "loader")?)?
        else {
            continue;
        };
        let dependencies = object(
            py,
            upstream_loader_dependency_names(&loader_function, &loader_functions)?,
        )?;
        for dependency_name in dependencies.try_iter()? {
            let dependency_name = dependency_name?;
            let dependency = mapping_get(source_map, &dependency_name)?;
            if dependency.is_none()
                || selected_names.contains(native_field(&dependency, "name")?)?
            {
                continue;
            }
            let table = native_field(&dependency, "table")?;
            let target = if table.is_truthy()? {
                table
            } else {
                native_field(&dependency, "name")?
            };
            if existing.contains(&target)? {
                continue;
            }
            let source_name = native_field(&source_entry, "name")?.str()?;
            return Err(error_of(
                py,
                ErrorId::PlannerInput,
                &format!(
                    "Source '{source_name}' requires intermediate loader '{}', but its target \
                     relation '{}' does not exist; use +source:{source_name} to refresh upstream \
                     ingress dependencies",
                    dependency_name.str()?,
                    target.str()?,
                ),
                &[],
            ));
        }
    }
    Ok(())
}

/// Build one canonical function entry from resolved relation inputs.
pub(super) fn function_entry<'py>(
    function: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
    relations: &Bound<'py, PyAny>,
    (fingerprint_query_sql, previous_query_sql, reason): (
        Bound<'py, PyAny>,
        Bound<'py, PyAny>,
        Bound<'py, PyAny>,
    ),
) -> PyResult<Bound<'py, PyAny>> {
    let py = function.py();
    let body_sql = resolve_function_sql(
        py,
        Some(keywords(
            py,
            &[
                ("adapter", adapter.clone()),
                ("function", function.clone()),
                (
                    "model_locations",
                    native_field(relations, "model_locations")?,
                ),
                ("seed_locations", native_field(relations, "seed_locations")?),
                (
                    "function_locations",
                    native_field(relations, "function_locations")?,
                ),
                ("source_map", native_field(relations, "source_read_map")?),
                (
                    "source_warehouse_columns",
                    native_field(relations, "source_warehouse_columns")?,
                ),
                (
                    "star_exclude_keyword",
                    native_field(relations, "star_exclude_keyword")?,
                ),
            ],
        )?),
    )?;
    let field = |name: &str| native_field(function, name);
    planner_model(
        py,
        RecordId::FunctionPlanEntry,
        &[
            ("key", field("key")?),
            ("name", field("name")?),
            ("relative_path", field("relative_path")?),
            ("destination", field("destination")?),
            ("arguments", field("arguments")?),
            ("returns", field("returns")?),
            ("body_sql", body_sql),
            ("fingerprint_query_sql", fingerprint_query_sql),
            ("fingerprint_destination", field("fingerprint_destination")?),
            ("return_columns", field("return_columns")?),
            ("language", field("language")?),
            ("source_file_path", field("source_file_path")?),
            ("runtime_version", field("runtime_version")?),
            ("entry_point", field("entry_point")?),
            ("packages", field("packages")?),
            ("previous_query_sql", previous_query_sql),
            ("reason", reason),
        ],
    )
}

fn function_entries<'py>(
    (project, adapter, snapshot): (&Bound<'py, PyAny>, &Bound<'py, PyAny>, &Bound<'py, PyAny>),
    relations: &Bound<'py, PyAny>,
    changes: &Bound<'py, PyAny>,
    selected_keys: &Bound<'py, PyAny>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py = project.py();
    let functions = native_field(changes, "functions")?;
    let previous = native_field(&native_field(snapshot, "fingerprints")?, "functions")?;
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    for function in native_field(project, "functions")?.try_iter()? {
        let function = function?;
        if !selected_keys.contains(native_field(&function, "key")?)? {
            continue;
        }
        let name = native_field(&function, "name")?;
        let change = functions.get_item(&name)?;
        let previous_query_sql = if previous.contains(&name)? {
            native_field(&previous.get_item(&name)?, "definition")?
        } else {
            none(py)
        };
        entries.push(function_entry(
            &function,
            adapter,
            relations,
            (
                native_field(&change, "fingerprint_sql")?,
                previous_query_sql,
                native_field(&change, "reason")?,
            ),
        )?);
    }
    Ok(entries)
}

/// Whether a test is named by the selection or covers a selected resource, and not excluded.
pub(super) fn test_selected(
    test: &Bound<'_, PyAny>,
    selected_keys: &Bound<'_, PyAny>,
    selection: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    let parent = native_field(test, "parent_name")?;
    let name = if parent.is_truthy()? {
        parent
    } else {
        native_field(test, "name")?
    };
    if native_field(selection, "excluded_names")?.contains(&name)? {
        return Ok(false);
    }
    Ok(native_field(selection, "names")?.contains(&name)?
        || scope_overlaps(&native_field(test, "scope_deps")?, selected_keys)?)
}

/// Planned SQL test entries and the warnings planning them produced.
pub(super) struct SelectedTests<'py> {
    pub(super) entries: Vec<Bound<'py, PyAny>>,
    pub(super) warnings: Vec<Bound<'py, PyAny>>,
}

/// Selected SQL test entries and their warnings, failing on invalid fixtures.
pub(super) fn selected_test_entries<'py>(
    (project, adapter): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    selected_keys: &Bound<'py, PyAny>,
    selection: &Bound<'py, PyAny>,
    case_name: &Bound<'py, PyAny>,
) -> PyResult<SelectedTests<'py>> {
    let py = project.py();
    let mut selected: Vec<Bound<'py, PyAny>> = Vec::new();
    for test in native_field(project, "sql_tests")?.try_iter()? {
        let test = test?;
        if !test_selected(&test, selected_keys, selection)? {
            continue;
        }
        if !case_name.is_none() && native_field(&test, "case_name")?.ne(case_name)? {
            continue;
        }
        selected.push(test);
    }
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut warnings: Vec<Bound<'py, PyAny>> = Vec::new();
    if selected.is_empty() {
        return Ok(SelectedTests { entries, warnings });
    }
    let analysis = native_field(&native_field(project, "settings")?, "sql_analysis")?;
    let fixture_context = if analysis.is_truthy()? {
        Bound::new(py, planning_context(project, None)?)?.into_any()
    } else {
        none(py)
    };
    let results = assemble_sql_test_plans(
        &selected,
        (project, adapter),
        &SqlTestAssembly {
            sql_analysis_enabled: analysis,
            validate_fixtures: true,
            fixture_planning_context: fixture_context,
        },
    )?;
    let mut diagnostics: Vec<String> = Vec::new();
    for result in results.try_iter()? {
        let result = result?;
        let entry = native_field(&result, "entry")?;
        if entry.is_none() {
            for diagnostic in native_field(&result, "fixture_diagnostics")?.try_iter()? {
                diagnostics.push(diagnostic?.str()?.to_string());
            }
            continue;
        }
        entries.push(entry);
        for warning in native_field(&result, "warnings")?.try_iter()? {
            warnings.push(warning?);
        }
    }
    if !diagnostics.is_empty() {
        return Err(error_of(
            py,
            ErrorId::PlannerInput,
            &format!("Invalid SQL test fixtures:\n- {}", diagnostics.join("\n- ")),
            &[],
        ));
    }
    Ok(SelectedTests { entries, warnings })
}

/// SQL tests selected by name or overlapping one selection, planned into a reusable result.
fn planned_sql_tests<'py>(
    project: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
    selected_keys: &Bound<'py, PyAny>,
    selection: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = project.py();
    let selected = selected_test_entries((project, adapter), selected_keys, selection, &none(py))?;
    native(
        py,
        RecordId::PlannedSqlTests,
        &[
            ("selected_keys", selected_keys.clone()),
            ("sql_test_selection", selection.clone()),
            ("entries", tuple_of(py, selected.entries)?),
            ("warnings", tuple_of(py, selected.warnings)?),
        ],
    )
}

/// The plan output's fields from planned entries and resolved relation inputs.
pub(crate) fn plan_output_fields<'py>(
    inputs: PlanOutputInputs<'py>,
) -> PyResult<Vec<(&'static str, Bound<'py, PyAny>)>> {
    let PlanOutputInputs {
        project,
        adapter,
        scope,
        snapshot,
        relations,
        changes,
        model_entries,
        model_warnings,
        reload_sources,
        extras,
    } = inputs;
    let py = project.py();
    let extras = if extras.is_none() {
        native(py, RecordId::PlanOutputExtras, &[])?
    } else {
        extras
    };
    let selected_keys = native_field(&scope, "selected_keys")?;
    let execution_order = native_field(&scope, "execution_order")?;
    let source_map = native_field(&relations, "source_map")?;
    let seeds = seed_entries(&project, &snapshot, &selected_keys, &extras)?;
    let source_load_entries = object(
        py,
        build_source_load_entries(
            &execution_order,
            &selected_keys,
            source_map.downcast::<PyDict>()?,
            reload_sources.is_truthy()?,
        )?,
    )?;
    require_intermediate_loader_targets(&project, &snapshot, &source_map, &source_load_entries)?;
    let functions = function_entries(
        (&project, &adapter, &snapshot),
        &relations,
        &changes,
        &selected_keys,
    )?;
    let materializations = PyDict::new(py);
    for entry in &model_entries {
        materializations.set_item(
            native_field(entry, "name")?,
            native_field(entry, "materialization_type")?,
        )?;
    }
    let audit_entries = object(
        py,
        build_selected_audit_entries(Some(&keywords(
            py,
            &[
                ("project", project.clone()),
                ("adapter", adapter.clone()),
                ("scope", scope.clone()),
                ("relations", relations.clone()),
                ("model_materializations", materializations.into_any()),
            ],
        )?))?,
    )?;
    let selection = native_field(&scope, "sql_test_selection")?;
    let mut planned = native_field(&extras, "planned_sql_tests")?;
    if planned.is_none()
        || native_field(&planned, "selected_keys")?.ne(&selected_keys)?
        || native_field(&planned, "sql_test_selection")?.ne(&selection)?
    {
        planned = planned_sql_tests(&project, &adapter, &selected_keys, &selection)?;
    }
    let test_entries = native_field(&planned, "entries")?;
    let mut test_keys: Vec<Bound<'py, PyAny>> = Vec::new();
    for entry in test_entries.try_iter()? {
        test_keys.push(native_field(&entry?, "key")?);
    }
    let scoped_keys = selected_keys.call_method1("__or__", (PyFrozenSet::new(py, test_keys)?,))?;
    let mut scoped_order: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in execution_order.try_iter()? {
        let key = key?;
        if scoped_keys.contains(&key)? {
            scoped_order.push(key);
        }
    }
    let mut warnings: Vec<Bound<'py, PyAny>> = model_warnings;
    for warning in native_field(&planned, "warnings")?.try_iter()? {
        warnings.push(warning?);
    }
    let model_entries = tuple_of(py, model_entries)?;
    Ok(vec![
        ("execution_order", tuple_of(py, scoped_order)?),
        ("model_entries", model_entries.clone()),
        ("seed_entries", tuple_of(py, seeds)?),
        (
            "source_load_entries",
            PyTuple::new(
                py,
                source_load_entries
                    .try_iter()?
                    .collect::<PyResult<Vec<_>>>()?,
            )?
            .into_any(),
        ),
        ("function_entries", tuple_of(py, functions)?),
        (
            "audit_entries",
            PyTuple::new(py, audit_entries.try_iter()?.collect::<PyResult<Vec<_>>>()?)?.into_any(),
        ),
        (
            "test_entries",
            PyTuple::new(py, test_entries.try_iter()?.collect::<PyResult<Vec<_>>>()?)?.into_any(),
        ),
        ("selected_keys", selected_keys),
        ("warnings", tuple_of(py, warnings)?),
        ("upstream_deps", native_field(&scope, "upstream_deps")?),
        ("downstream_deps", native_field(&scope, "downstream_deps")?),
        (
            "model_locations",
            native_field(&relations, "model_locations")?,
        ),
        (
            "seed_locations",
            native_field(&relations, "seed_locations")?,
        ),
        (
            "function_locations",
            native_field(&relations, "function_locations")?,
        ),
        ("source_map", source_map),
        (
            "source_read_map",
            native_field(&relations, "source_read_map")?,
        ),
        (
            "python_source_read_map",
            native_field(&relations, "python_source_read_map")?,
        ),
        ("hook_functions", native_field(&project, "hook_functions")?),
        (
            "enforce_explicit_references",
            native_field(&project, "enforce_explicit_references")?,
        ),
        (
            "provider_usages",
            plan_provider_usages(&project, &model_entries, &source_load_entries)?,
        ),
        (
            "python_identity_fingerprints",
            native_field(&native_field(&snapshot, "fingerprints")?, "python_nodes")?,
        ),
    ])
}

/// Build one canonical function entry from resolved relation inputs.
#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn plan_function<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "plan_function",
        kwargs,
        (
            &["function", "adapter", "relations", "fingerprint_query_sql"],
            &["previous_query_sql", "reason"],
        ),
    )?;
    let reason = if args.passed("reason")? {
        args.value("reason")?
    } else {
        planner_type(py, RecordId::PlanReason, "NO_CHANGE")?
    };
    function_entry(
        &args.value("function")?,
        &args.value("adapter")?,
        &args.value("relations")?,
        (
            args.value("fingerprint_query_sql")?,
            args.value("previous_query_sql")?,
            reason,
        ),
    )
}

/// Plan SQL tests selected by name or overlapping one selection into a reusable result.
#[pyfunction]
#[pyo3(signature = (*, project, adapter, selected_keys, sql_test_selection))]
pub(crate) fn plan_selected_sql_tests<'py>(
    project: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
    selected_keys: &Bound<'py, PyAny>,
    sql_test_selection: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    planned_sql_tests(project, adapter, selected_keys, sql_test_selection)
}

/// Whether a test is named by the selection or covers a selected resource, and not excluded.
#[pyfunction]
#[pyo3(signature = (*, test, selected_keys, sql_test_selection))]
fn sql_test_is_selected(
    test: &Bound<'_, PyAny>,
    selected_keys: &Bound<'_, PyAny>,
    sql_test_selection: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    test_selected(test, selected_keys, sql_test_selection)
}

/// Selected SQL test entries and warnings, optionally narrowed to one parameterized case.
#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn build_selected_test_entries<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<(Bound<'py, PyList>, Bound<'py, PyList>)> {
    let args = KeywordArguments::read(
        py,
        "build_selected_test_entries",
        kwargs,
        (
            &["project", "adapter", "selected_keys", "sql_test_selection"],
            &["case_name"],
        ),
    )?;
    let selected = selected_test_entries(
        (&args.value("project")?, &args.value("adapter")?),
        &args.value("selected_keys")?,
        &args.value("sql_test_selection")?,
        &args.value("case_name")?,
    )?;
    Ok((
        PyList::new(py, selected.entries)?,
        PyList::new(py, selected.warnings)?,
    ))
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(plan_function, module)?)?;
    module.add_function(wrap_pyfunction!(plan_selected_sql_tests, module)?)?;
    module.add_function(wrap_pyfunction!(sql_test_is_selected, module)?)?;
    module.add_function(wrap_pyfunction!(sql_test_model_chain_names_by_key, module)?)?;
    module.add_function(wrap_pyfunction!(build_selected_test_entries, module)?)
}
