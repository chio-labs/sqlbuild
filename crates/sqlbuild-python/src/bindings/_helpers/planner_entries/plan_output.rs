//! `PlanOutput` assembly from planned model entries, seeds, sources, functions, audits and tests.

use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, imported};
use crate::bindings::_helpers::planner_entries::model_entries::scope_overlaps;
use crate::bindings::_helpers::planner_entries::values::{
    DISCOVERY_MODELS, PLANNER_EXCEPTIONS, error_of, native, none, planner_model, planner_type,
    string,
};
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
        return mapping.call_method1("get", (key,));
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
        lookup.set_item(item.getattr("name")?, item)?;
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
    if !snapshot
        .getattr("existing_relations")?
        .contains(seed_name)?
    {
        return planner_type(py, "PlanReason", "FIRST_RUN");
    }
    let fingerprint = snapshot
        .getattr("fingerprints")?
        .getattr("seeds")?
        .call_method1("get", (seed_name,))?;
    if fingerprint.is_none() {
        return planner_type(py, "PlanReason", "FIRST_RUN");
    }
    if !expected_version_hash.is_none()
        && fingerprint
            .getattr("version_hash")?
            .ne(expected_version_hash)?
    {
        return planner_type(py, "PlanReason", "CONFIG_CHANGED");
    }
    planner_type(py, "PlanReason", "NO_CHANGE")
}

fn seed_entries<'py>(
    project: &Bound<'py, PyAny>,
    snapshot: &Bound<'py, PyAny>,
    selected_keys: &Bound<'py, PyAny>,
    extras: &Bound<'py, PyAny>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py = project.py();
    let version_hashes = extras.getattr("seed_version_hashes")?;
    let metadata_jsons = extras.getattr("seed_metadata_jsons")?;
    let plan_reasons = extras.getattr("seed_plan_reasons")?;
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    for seed in project.getattr("seeds")?.try_iter()? {
        let seed = seed?;
        if !selected_keys.contains(seed.getattr("key")?)? {
            continue;
        }
        let name = seed.getattr("name")?;
        entries.push(planner_model(
            py,
            "SeedPlanEntry",
            &[
                ("key", seed.getattr("key")?),
                ("name", name.clone()),
                ("destination", seed.getattr("destination")?),
                (
                    "file_path",
                    seed.getattr("seed_file")?.getattr("file_path")?,
                ),
                (
                    "columns",
                    native(py, "extract_seed_columns", &[("seed", seed.clone())])?,
                ),
                (
                    "csv_settings",
                    seed.getattr("schema_entry")?.getattr("csv_settings")?,
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
        usages.push(planner_model(
            py,
            "PlanProviderUsage",
            &[
                ("provider_name", usage.getattr("provider_name")?),
                ("consumer_kind", string(py, consumer_kind)),
                ("consumer_name", consumer_name.clone()),
                ("parameter_name", usage.getattr("parameter_name")?),
                (
                    "annotation_class_name",
                    usage.getattr("annotation_class_name")?,
                ),
                ("annotation_module", usage.getattr("annotation_module")?),
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
    let python_hook = imported(py, DISCOVERY_MODELS, "PythonHookEntry")?;
    let mut hooks: Vec<Bound<'py, PyAny>> = Vec::new();
    for field in ["pre_hooks", "post_hooks"] {
        let hook_entry = entry.getattr(field)?;
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
        let Some(discovered) = hook_by_name.get_item(hook.getattr("name")?)? else {
            continue;
        };
        usages.extend(provider_usages(
            &discovered.getattr("provider_usages")?,
            HOOK_CONSUMER,
            &discovered.getattr("name")?,
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
    let loader_by_name = by_name(&project.getattr("loader_functions")?)?;
    for entry in source_load_entries.try_iter()? {
        let Some(loader) = loader_by_name.get_item(entry?.getattr("loader")?)? else {
            continue;
        };
        usages.extend(provider_usages(
            &loader.getattr("provider_usages")?,
            LOADER_CONSUMER,
            &loader.getattr("name")?,
        )?);
    }
    let hook_by_name = by_name(&project.getattr("hook_functions")?)?;
    let materialization_by_name = by_name(&project.getattr("materialization_files")?)?;
    for entry in model_entries.try_iter()? {
        let entry = entry?;
        usages.extend(hook_provider_usages(&entry, &hook_by_name)?);
        let custom = entry.getattr("custom_materialization_name")?;
        if custom.is_none() {
            continue;
        }
        let Some(materialization) = materialization_by_name.get_item(custom)? else {
            continue;
        };
        usages.extend(provider_usages(
            &materialization.getattr("provider_usages")?,
            MATERIALIZATION_CONSUMER,
            &materialization.getattr("name")?,
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
    let loader_functions = project.getattr("loader_functions")?;
    let loader_by_name = by_name(&loader_functions)?;
    let selected_names = PyFrozenSet::new(
        py,
        source_load_entries
            .try_iter()?
            .map(|entry| entry?.getattr("name"))
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    let existing = snapshot.getattr("existing_relations")?;
    for entry in source_load_entries.try_iter()? {
        let source_entry = source_map.call_method1("get", (entry?.getattr("name")?,))?;
        if source_entry.is_none() || source_entry.getattr("loader")?.is_none() {
            continue;
        }
        let Some(loader_function) = loader_by_name.get_item(source_entry.getattr("loader")?)?
        else {
            continue;
        };
        let dependencies = native(
            py,
            "upstream_loader_dependency_names",
            &[
                ("loader_function", loader_function),
                ("loader_functions", loader_functions.clone()),
            ],
        )?;
        for dependency_name in dependencies.try_iter()? {
            let dependency_name = dependency_name?;
            let dependency = source_map.call_method1("get", (&dependency_name,))?;
            if dependency.is_none() || selected_names.contains(dependency.getattr("name")?)? {
                continue;
            }
            let table = dependency.getattr("table")?;
            let target = if table.is_truthy()? {
                table
            } else {
                dependency.getattr("name")?
            };
            if existing.contains(&target)? {
                continue;
            }
            let source_name = source_entry.getattr("name")?.str()?;
            return Err(error_of(
                py,
                (PLANNER_EXCEPTIONS, "PlannerInputError"),
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
    let body_sql = native(
        py,
        "resolve_function_sql",
        &[
            ("adapter", adapter.clone()),
            ("function", function.clone()),
            ("model_locations", relations.getattr("model_locations")?),
            ("seed_locations", relations.getattr("seed_locations")?),
            (
                "function_locations",
                relations.getattr("function_locations")?,
            ),
            ("source_map", relations.getattr("source_read_map")?),
            (
                "source_warehouse_columns",
                relations.getattr("source_warehouse_columns")?,
            ),
            (
                "star_exclude_keyword",
                relations.getattr("star_exclude_keyword")?,
            ),
        ],
    )?;
    let field = |name: &str| function.getattr(name);
    planner_model(
        py,
        "FunctionPlanEntry",
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
    let functions = changes.getattr("functions")?;
    let previous = snapshot.getattr("fingerprints")?.getattr("functions")?;
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    for function in project.getattr("functions")?.try_iter()? {
        let function = function?;
        if !selected_keys.contains(function.getattr("key")?)? {
            continue;
        }
        let name = function.getattr("name")?;
        let change = functions.get_item(&name)?;
        let previous_query_sql = if previous.contains(&name)? {
            previous.get_item(&name)?.getattr("definition")?
        } else {
            none(py)
        };
        entries.push(function_entry(
            &function,
            adapter,
            relations,
            (
                change.getattr("fingerprint_sql")?,
                previous_query_sql,
                change.getattr("reason")?,
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
    let parent = test.getattr("parent_name")?;
    let name = if parent.is_truthy()? {
        parent
    } else {
        test.getattr("name")?
    };
    if selection.getattr("excluded_names")?.contains(&name)? {
        return Ok(false);
    }
    Ok(selection.getattr("names")?.contains(&name)?
        || scope_overlaps(&test.getattr("scope_deps")?, selected_keys)?)
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
    for test in project.getattr("sql_tests")?.try_iter()? {
        let test = test?;
        if !test_selected(&test, selected_keys, selection)? {
            continue;
        }
        if !case_name.is_none() && test.getattr("case_name")?.ne(case_name)? {
            continue;
        }
        selected.push(test);
    }
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut warnings: Vec<Bound<'py, PyAny>> = Vec::new();
    if selected.is_empty() {
        return Ok(SelectedTests { entries, warnings });
    }
    let analysis = project.getattr("settings")?.getattr("sql_analysis")?;
    let fixture_context = if analysis.is_truthy()? {
        native(
            py,
            "build_relation_fixture_context",
            &[("project", project.clone())],
        )?
    } else {
        none(py)
    };
    let results = native(
        py,
        "plan_sql_tests",
        &[
            ("tests", tuple_of(py, selected)?),
            ("project", project.clone()),
            ("adapter", adapter.clone()),
            ("sql_analysis_enabled", analysis),
            (
                "validate_fixtures",
                pyo3::types::PyBool::new(py, true).to_owned().into_any(),
            ),
            ("fixture_planning_context", fixture_context),
        ],
    )?;
    let mut diagnostics: Vec<String> = Vec::new();
    for result in results.try_iter()? {
        let result = result?;
        let entry = result.getattr("entry")?;
        if entry.is_none() {
            for diagnostic in result.getattr("fixture_diagnostics")?.try_iter()? {
                diagnostics.push(diagnostic?.str()?.to_string());
            }
            continue;
        }
        entries.push(entry);
        for warning in result.getattr("warnings")?.try_iter()? {
            warnings.push(warning?);
        }
    }
    if !diagnostics.is_empty() {
        return Err(error_of(
            py,
            (PLANNER_EXCEPTIONS, "PlannerInputError"),
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
    planner_model(
        py,
        "PlannedSqlTests",
        &[
            ("selected_keys", selected_keys.clone()),
            ("sql_test_selection", selection.clone()),
            ("entries", tuple_of(py, selected.entries)?),
            ("warnings", tuple_of(py, selected.warnings)?),
        ],
    )
}

fn plan_output<'py>(args: &KeywordArguments<'py>) -> PyResult<Bound<'py, PyAny>> {
    let project = args.value("project")?;
    let py = project.py();
    let adapter = args.value("adapter")?;
    let scope = args.value("scope")?;
    let snapshot = args.value("snapshot")?;
    let relations = args.value("relations")?;
    let model_entry_results = args.value("model_entry_results")?;
    let extras = args.value("extras")?;
    let extras = if extras.is_none() {
        planner_model(py, "PlanOutputExtras", &[])?
    } else {
        extras
    };
    let selected_keys = scope.getattr("selected_keys")?;
    let execution_order = scope.getattr("execution_order")?;
    let source_map = relations.getattr("source_map")?;
    let seeds = seed_entries(&project, &snapshot, &selected_keys, &extras)?;
    let source_load_entries = native(
        py,
        "build_source_load_entries",
        &[
            ("execution_order", execution_order.clone()),
            ("selected_keys", selected_keys.clone()),
            ("source_map", source_map.clone()),
            ("is_reload", args.value("reload_sources")?),
        ],
    )?;
    require_intermediate_loader_targets(&project, &snapshot, &source_map, &source_load_entries)?;
    let functions = function_entries(
        (&project, &adapter, &snapshot),
        &relations,
        &args.value("changes")?,
        &selected_keys,
    )?;
    let model_entries = model_entry_results.getattr("entries")?;
    let materializations = PyDict::new(py);
    for entry in model_entries.try_iter()? {
        let entry = entry?;
        materializations.set_item(
            entry.getattr("name")?,
            entry.getattr("materialization_type")?,
        )?;
    }
    let audit_entries = native(
        py,
        "build_selected_audit_entries",
        &[
            ("project", project.clone()),
            ("adapter", adapter.clone()),
            ("scope", scope.clone()),
            ("relations", relations.clone()),
            ("model_materializations", materializations.into_any()),
        ],
    )?;
    let selection = scope.getattr("sql_test_selection")?;
    let mut planned = extras.getattr("planned_sql_tests")?;
    if planned.is_none()
        || planned.getattr("selected_keys")?.ne(&selected_keys)?
        || planned.getattr("sql_test_selection")?.ne(&selection)?
    {
        planned = planned_sql_tests(&project, &adapter, &selected_keys, &selection)?;
    }
    let test_entries = planned.getattr("entries")?;
    let mut test_keys: Vec<Bound<'py, PyAny>> = Vec::new();
    for entry in test_entries.try_iter()? {
        test_keys.push(entry?.getattr("key")?);
    }
    let scoped_keys = selected_keys.call_method1("__or__", (PyFrozenSet::new(py, test_keys)?,))?;
    let mut scoped_order: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in execution_order.try_iter()? {
        let key = key?;
        if scoped_keys.contains(&key)? {
            scoped_order.push(key);
        }
    }
    let mut warnings: Vec<Bound<'py, PyAny>> = Vec::new();
    for warning in model_entry_results.getattr("warnings")?.try_iter()? {
        warnings.push(warning?);
    }
    for warning in planned.getattr("warnings")?.try_iter()? {
        warnings.push(warning?);
    }
    planner_model(
        py,
        "PlanOutput",
        &[
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
                PyTuple::new(py, audit_entries.try_iter()?.collect::<PyResult<Vec<_>>>()?)?
                    .into_any(),
            ),
            (
                "test_entries",
                PyTuple::new(py, test_entries.try_iter()?.collect::<PyResult<Vec<_>>>()?)?
                    .into_any(),
            ),
            ("selected_keys", selected_keys),
            ("warnings", tuple_of(py, warnings)?),
            ("upstream_deps", scope.getattr("upstream_deps")?),
            ("downstream_deps", scope.getattr("downstream_deps")?),
            ("model_locations", relations.getattr("model_locations")?),
            ("seed_locations", relations.getattr("seed_locations")?),
            (
                "function_locations",
                relations.getattr("function_locations")?,
            ),
            ("source_map", source_map),
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
            (
                "provider_usages",
                plan_provider_usages(&project, &model_entries, &source_load_entries)?,
            ),
            (
                "python_identity_fingerprints",
                snapshot.getattr("fingerprints")?.getattr("python_nodes")?,
            ),
        ],
    )
}

/// Assemble the plan output from planned entries and resolved relation inputs.
#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn build_plan_output<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "build_plan_output",
        kwargs,
        (
            &[
                "project",
                "adapter",
                "scope",
                "snapshot",
                "relations",
                "changes",
                "model_entry_results",
                "reload_sources",
            ],
            &["extras"],
        ),
    )?;
    plan_output(&args)
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
        planner_type(py, "PlanReason", "NO_CHANGE")?
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
fn plan_selected_sql_tests<'py>(
    project: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
    selected_keys: &Bound<'py, PyAny>,
    sql_test_selection: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    planned_sql_tests(project, adapter, selected_keys, sql_test_selection)
}

/// Plan selected SQL tests into `future`, which re-raises any failure on the joining thread.
#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn plan_selected_sql_tests_into<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<()> {
    let args = KeywordArguments::read(
        py,
        "plan_selected_sql_tests_into",
        kwargs,
        (
            &[
                "future",
                "project",
                "adapter",
                "selected_keys",
                "sql_test_selection",
            ],
            &[],
        ),
    )?;
    let future = args.value("future")?;
    match native(
        py,
        "plan_selected_sql_tests",
        &[
            ("project", args.value("project")?),
            ("adapter", args.value("adapter")?),
            ("selected_keys", args.value("selected_keys")?),
            ("sql_test_selection", args.value("sql_test_selection")?),
        ],
    ) {
        Ok(planned) => future.call_method1("set_result", (planned,))?,
        Err(error) => future.call_method1("set_exception", (error.value(future.py()),))?,
    };
    Ok(())
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
    module.add_function(wrap_pyfunction!(build_plan_output, module)?)?;
    module.add_function(wrap_pyfunction!(plan_function, module)?)?;
    module.add_function(wrap_pyfunction!(plan_selected_sql_tests, module)?)?;
    module.add_function(wrap_pyfunction!(plan_selected_sql_tests_into, module)?)?;
    module.add_function(wrap_pyfunction!(sql_test_is_selected, module)?)?;
    module.add_function(wrap_pyfunction!(build_selected_test_entries, module)?)
}
