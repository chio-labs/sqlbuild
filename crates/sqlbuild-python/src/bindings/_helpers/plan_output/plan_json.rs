//! The JSON plan document, read from the planner's output by attribute.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyListMethods, PyString};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, imported};
use crate::bindings::_helpers::compile_outputs::json_report::indented_json;
use crate::bindings::_helpers::plan_output::cursor_details::{
    CursorDetails, cursor_details, owner,
};
use crate::bindings::_helpers::plan_output::python_identity::{
    definition_source_text, dependency_source_text,
};
use crate::bindings::_helpers::plan_output::safety::{future_cursor_safety, maximum_start_safety};
use crate::bindings::_helpers::plan_output::values::{
    any, dict, enum_value, iso, items, list, mapped, optional_enum_value, relation_name, text,
};

const SENTINEL_TOKEN_MODULE: &str = "sqlbuild.cursor_algebra.main.sentinel_to_token";
const MICROBATCH_MODE: &str = "microbatch";
const RENAMED_REASON: &str = "renamed";
const RENAMED_DECISION: &str = "renamed";
const VIEW_MATERIALIZATION: &str = "view";
const CHANGED_IDENTITY: &str = "changed";

fn token<'py>(bound: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = bound.py();
    let keywords: Bound<'py, PyDict> = PyDict::new(py);
    keywords.set_item("sentinel", bound)?;
    imported(py, SENTINEL_TOKEN_MODULE, "sentinel_to_token")?.call((), Some(&keywords))
}

fn token_bounds<'py>(bounds: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    Ok(dict(
        bounds.py(),
        vec![
            ("start", token(bounds.getattr("start")?)?),
            ("end", token(bounds.getattr("end")?)?),
        ],
    )?
    .into_any())
}

/// `_serialize_cursor_details`: requested, resolved and deferred cursor-plan state.
fn cursor_json<'py>(py: Python<'py>, details: &CursorDetails<'py>) -> PyResult<Bound<'py, PyAny>> {
    let resolved: Bound<'py, PyAny> = match &details.resolved_bounds {
        Some(bounds) => token_bounds(bounds)?,
        None => py.None().into_bound(py),
    };
    Ok(dict(
        py,
        vec![
            (
                "requested_bounds",
                dict(
                    py,
                    vec![
                        ("start", any(py, details.requested_start.clone())?),
                        ("end", any(py, details.requested_end.clone())?),
                    ],
                )?
                .into_any(),
            ),
            ("bounds_owner", any(py, owner(details))?),
            ("resolution_status", any(py, details.resolution_status)?),
            ("resolved_bounds", resolved),
            ("declared_grain", any(py, details.declared_grain.clone())?),
            ("effective_grain", any(py, details.effective_grain.clone())?),
            (
                "declared_batch_size",
                any(py, details.declared_batch_size.clone())?,
            ),
            (
                "effective_batch_size",
                any(py, details.effective_batch_size.clone())?,
            ),
            ("planned_batch_count", any(py, details.planned_batch_count)?),
            ("empty_inputs", list(&details.empty_inputs)?),
            (
                "waiting_on_empty_inputs",
                any(py, details.waiting_on_empty_inputs)?,
            ),
        ],
    )?
    .into_any())
}

fn identity_status(entry: &Bound<'_, PyAny>) -> PyResult<&'static str> {
    let expected: Bound<'_, PyAny> = entry.getattr("fingerprint_version_hash")?;
    let built: Bound<'_, PyAny> = entry.getattr("previous_version_hash")?;
    Ok(if expected.is_none() {
        "unknown"
    } else if built.is_none() {
        "missing"
    } else if built.eq(&expected)? {
        "current"
    } else {
        "stale"
    })
}

/// The safety evidence of the microbatch range when it has some, else of the cursor bounds.
fn evidence<'py>(entry: &Bound<'py, PyAny>, field: &str) -> PyResult<Bound<'py, PyAny>> {
    let microbatch_range: Bound<'py, PyAny> = entry.getattr("microbatch_range")?;
    if !microbatch_range.is_none() {
        let found: Bound<'py, PyAny> = microbatch_range.getattr(field)?;
        if !found.is_none() {
            return Ok(found);
        }
    }
    let bounds: Bound<'py, PyAny> = entry.getattr("cursor_bounds")?;
    if bounds.is_none() {
        return Ok(bounds);
    }
    bounds.getattr(field)
}

fn microbatch_state<'py>(entry: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = entry.py();
    let state: Bound<'py, PyDict> = dict(
        py,
        vec![
            ("completion_tracking", any(py, "universal")?),
            ("batch_concurrency", entry.getattr("batch_concurrency")?),
            (
                "unaccounted_partition_policy",
                entry.getattr("unaccounted_partition_policy")?,
            ),
            ("reconciliation", any(py, "runtime")?),
        ],
    )?;
    let limit: Bound<'py, PyAny> = entry.getattr("microbatch_limit")?;
    if !limit.is_none() {
        state.set_item("limit", limit)?;
        state.set_item("count", entry.getattr("microbatch_limit_count")?)?;
        state.set_item(
            "action",
            optional_enum_value(&entry.getattr("microbatch_limit_action")?)?,
        )?;
        state.set_item("warning", entry.getattr("microbatch_limit_warning")?)?;
    }
    Ok(state.into_any())
}

fn model_json<'py>(entry: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = entry.py();
    let model: Bound<'py, PyDict> = dict(
        py,
        vec![
            ("name", entry.getattr("name")?),
            (
                "relative_path",
                entry.getattr("relative_path")?.str()?.into_any(),
            ),
            (
                "materialization_type",
                enum_value(entry, "materialization_type")?,
            ),
            ("action", enum_value(entry, "action")?),
            ("reason", enum_value(entry, "reason")?),
            (
                "expected_version_hash",
                entry.getattr("fingerprint_version_hash")?,
            ),
            (
                "built_version_hash",
                entry.getattr("previous_version_hash")?,
            ),
            (
                "built_version_present",
                any(py, !entry.getattr("previous_version_hash")?.is_none())?,
            ),
            ("identity_status", any(py, identity_status(entry)?)?),
        ],
    )?;
    for key in ["incremental_strategy", "incremental_mode"] {
        let value: Bound<'py, PyAny> = entry.getattr(key)?;
        if !value.is_none() {
            model.set_item(key, value)?;
        }
    }
    if entry.getattr("incremental_mode")?.eq(MICROBATCH_MODE)? {
        model.set_item("microbatch_state", microbatch_state(entry)?)?;
    }
    for key in ["cursor_column", "cursor_type"] {
        let value: Bound<'py, PyAny> = entry.getattr(key)?;
        if !value.is_none() {
            model.set_item(key, value)?;
        }
    }
    let bounds: Bound<'py, PyAny> = entry.getattr("cursor_bounds")?;
    if !bounds.is_none() {
        model.set_item("cursor_bounds", token_bounds(&bounds)?)?;
    }
    let future: Bound<'py, PyAny> = future_cursor_safety(&evidence(entry, "future_safety")?)?;
    if !future.is_none() {
        model.set_item("future_cursor_safety", future)?;
    }
    let maximum: Bound<'py, PyAny> =
        maximum_start_safety(&evidence(entry, "maximum_start_safety")?)?;
    if !maximum.is_none() {
        model.set_item("maximum_start_safety", maximum)?;
    }
    if let Some(details) = cursor_details(entry)? {
        model.set_item("cursor", cursor_json(py, &details)?)?;
    }
    let backfill: Bound<'py, PyAny> = entry.getattr("backfill")?;
    model.set_item(
        "backfill",
        dict(
            py,
            vec![
                ("action", enum_value(&backfill, "action")?),
                ("duration", backfill.getattr("duration")?),
            ],
        )?,
    )?;
    if entry.getattr("reason")?.eq(RENAMED_REASON)?
        && entry.getattr("query_changed")?.is_truthy()?
    {
        model.set_item("query_changed", true)?;
    }
    let changed_functions: Bound<'py, PyAny> = entry.getattr("changed_functions")?;
    if changed_functions.is_truthy()? {
        model.set_item("changed_functions", list(&changed_functions)?)?;
    }
    let qualified: Bound<'py, PyAny> = entry.getattr("destination")?.getattr("qualified_name")?;
    if !qualified.is_none() {
        model.set_item("qualified_name", qualified)?;
    }
    let hints: Bound<'py, PyAny> = entry.getattr("column_rename_hints")?;
    if hints.is_truthy()? {
        model.set_item(
            "column_rename_hints",
            mapped(&hints, |hint| {
                Ok(dict(
                    py,
                    vec![
                        ("column", hint.getattr("added_column")?),
                        ("candidates", list(&hint.getattr("candidate_columns")?)?),
                        ("identical", hint.getattr("identical")?),
                        ("hint", hint.getattr("message")?),
                    ],
                )?
                .into_any())
            })?,
        )?;
    }
    Ok(model.into_any())
}

fn with_qualified_name<'py>(
    item: Bound<'py, PyDict>,
    entry: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let qualified: Bound<'py, PyAny> = entry.getattr("destination")?.getattr("qualified_name")?;
    if !qualified.is_none() {
        item.set_item("qualified_name", qualified)?;
    }
    Ok(item.into_any())
}

fn seed_json<'py>(entry: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = entry.py();
    with_qualified_name(
        dict(
            py,
            vec![
                ("name", entry.getattr("name")?),
                ("reason", enum_value(entry, "reason")?),
            ],
        )?,
        entry,
    )
}

fn source_load_json<'py>(entry: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = entry.py();
    let load: Bound<'py, PyDict> = dict(
        py,
        vec![
            ("name", entry.getattr("name")?),
            ("loader", entry.getattr("loader")?),
            ("kind", enum_value(entry, "resource_kind")?),
            ("target", entry.getattr("destination")?),
            ("is_reload", entry.getattr("is_reload")?),
        ],
    )?;
    let strategy: Bound<'py, PyAny> = entry.getattr("write_strategy")?;
    if !strategy.is_none() {
        load.set_item("write_strategy", strategy.getattr("value")?)?;
    }
    let cursor: Bound<'py, PyAny> = entry.getattr("cursor_column")?;
    if !cursor.is_none() {
        load.set_item("cursor_column", cursor)?;
    }
    let unique_key: Bound<'py, PyAny> = entry.getattr("unique_key")?;
    if unique_key.is_truthy()? {
        load.set_item("unique_key", unique_key)?;
    }
    Ok(load.into_any())
}

fn function_json<'py>(entry: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = entry.py();
    let columns: Bound<'py, PyAny> = entry.getattr("return_columns")?;
    with_qualified_name(
        dict(
            py,
            vec![
                ("name", entry.getattr("name")?),
                (
                    "relative_path",
                    entry.getattr("relative_path")?.str()?.into_any(),
                ),
                ("language", enum_value(entry, "language")?),
                (
                    "return_kind",
                    any(
                        py,
                        if columns.is_truthy()? {
                            "table"
                        } else {
                            "scalar"
                        },
                    )?,
                ),
                ("returns", entry.getattr("returns")?),
                (
                    "return_columns",
                    mapped(&columns, |column| {
                        Ok(dict(
                            py,
                            vec![
                                ("name", column.getattr("name")?),
                                ("type", column.getattr("type")?),
                            ],
                        )?
                        .into_any())
                    })?,
                ),
            ],
        )?,
        entry,
    )
}

fn warning_json<'py>(warning: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = warning.py();
    let item: Bound<'py, PyDict> = dict(
        py,
        vec![
            ("severity", enum_value(warning, "severity")?),
            ("message", warning.getattr("message")?),
        ],
    )?;
    for key in ["model_name", "code"] {
        let value: Bound<'py, PyAny> = warning.getattr(key)?;
        if !value.is_none() {
            item.set_item(key, value)?;
        }
    }
    Ok(item.into_any())
}

/// `difflib.unified_diff` between two texts, each line without its newline.
fn unified_diff<'py>(py: Python<'py>, previous: &str, current: &str) -> PyResult<Vec<String>> {
    let lines = |text: &str| -> PyResult<Bound<'py, PyAny>> {
        PyString::new(py, text).call_method1("splitlines", (true,))
    };
    let keywords: Bound<'py, PyDict> = PyDict::new(py);
    keywords.set_item("fromfile", "previous")?;
    keywords.set_item("tofile", "current")?;
    let diff: Bound<'py, PyAny> = py
        .import("difflib")?
        .getattr("unified_diff")?
        .call((lines(previous)?, lines(current)?), Some(&keywords))?;
    let mut rendered: Vec<String> = Vec::new();
    for line in diff.try_iter()? {
        let line: String = line?.extract()?;
        rendered.push(line.trim_end_matches('\n').to_owned());
    }
    Ok(rendered)
}

fn identity_diff<'py>(entry: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = entry.py();
    let result: Bound<'py, PyDict> = PyDict::new(py);
    if !entry.getattr("identity_status")?.eq(CHANGED_IDENTITY)? {
        return Ok(result);
    }
    let pairs = [
        (
            "source_diff",
            definition_source_text(&entry.getattr("previous_definition_json")?)?,
            definition_source_text(&entry.getattr("current_definition_json")?)?,
        ),
        (
            "dependency_diff",
            dependency_source_text(&entry.getattr("previous_metadata_json")?)?,
            dependency_source_text(&entry.getattr("current_metadata_json")?)?,
        ),
    ];
    for (key, previous, current) in pairs {
        if let (Some(previous), Some(current)) = (previous, current)
            && previous != current
        {
            let diff: Vec<String> = unified_diff(py, &previous, &current)?;
            if !diff.is_empty() {
                result.set_item(key, diff)?;
            }
        }
    }
    Ok(result)
}

fn python_entry_json<'py>(entry: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = entry.py();
    let item: Bound<'py, PyDict> = dict(
        py,
        vec![
            ("name", entry.getattr("name")?),
            ("kind", enum_value(entry, "kind")?),
            ("phase", enum_value(entry, "phase")?),
            ("identity_status", enum_value(entry, "identity_status")?),
        ],
    )?;
    let diff: Bound<'py, PyDict> = identity_diff(entry)?;
    if !diff.is_empty() {
        item.set_item("identity_diff", diff)?;
    }
    Ok(item.into_any())
}

/// One provider usage: `(provider, kind, name, parameter, annotation class, annotation module)`.
type Usage<'py> = (
    String,
    (String, String, String),
    Bound<'py, PyAny>,
    Bound<'py, PyAny>,
);

fn providers_json<'py>(
    plan: &Bound<'py, PyAny>,
    python_entries: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = plan.py();
    let mut usages: Vec<Usage<'py>> = Vec::new();
    for usage in items(&plan.getattr("provider_usages")?)? {
        usages.push((
            text(&usage.getattr("provider_name")?)?,
            (
                text(&usage.getattr("consumer_kind")?)?,
                text(&usage.getattr("consumer_name")?)?,
                text(&usage.getattr("parameter_name")?)?,
            ),
            usage.getattr("annotation_class_name")?,
            usage.getattr("annotation_module")?,
        ));
    }
    for entry in python_entries {
        let kind: String = text(&enum_value(entry, "kind")?)?;
        let name: String = text(&entry.getattr("name")?)?;
        for usage in items(&entry.getattr("provider_usages")?)? {
            usages.push((
                text(&usage.getattr("provider_name")?)?,
                (
                    kind.clone(),
                    name.clone(),
                    text(&usage.getattr("parameter_name")?)?,
                ),
                usage.getattr("annotation_class_name")?,
                usage.getattr("annotation_module")?,
            ));
        }
    }
    usages.sort_by(|left, right| (&left.0, &left.1).cmp(&(&right.0, &right.1)));
    let providers: Bound<'py, PyList> = PyList::empty(py);
    let mut current: Option<(String, Bound<'py, PyList>)> = None;
    for (provider, (kind, name, parameter), class_name, module) in usages {
        if current.as_ref().is_none_or(|(open, _)| *open != provider) {
            let used_by: Bound<'py, PyList> = PyList::empty(py);
            providers.append(dict(
                py,
                vec![
                    ("name", any(py, provider.as_str())?),
                    ("used_by", used_by.clone().into_any()),
                ],
            )?)?;
            current = Some((provider, used_by));
        }
        let usage: Bound<'py, PyDict> = dict(
            py,
            vec![
                ("kind", any(py, kind)?),
                ("name", any(py, name)?),
                ("parameter", any(py, parameter)?),
            ],
        )?;
        if !class_name.is_none() || !module.is_none() {
            usage.set_item(
                "annotation",
                dict(py, vec![("class_name", class_name), ("module", module)])?,
            )?;
        }
        if let Some((_, used_by)) = &current {
            used_by.append(usage)?;
        }
    }
    Ok(providers.into_any())
}

fn old_name_json<'py>(entry: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = entry.py();
    Ok(dict(
        py,
        vec![
            ("model", entry.getattr("model_name")?),
            ("action", enum_value(entry, "action")?),
            ("view", relation_name(&entry.getattr("origin")?)?),
            ("reads", relation_name(&entry.getattr("destination")?)?),
            ("expires_at", iso(&entry.getattr("expires_at")?)?),
            (
                "column_aliases",
                py.import("builtins")?
                    .getattr("dict")?
                    .call1((entry.getattr("column_aliases")?,))?,
            ),
            ("grants_copied", entry.getattr("grants_copied")?),
            ("reason", entry.getattr("reason")?),
        ],
    )?
    .into_any())
}

fn migrations_json<'py>(plan: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = plan.py();
    let old_names: Bound<'py, PyDict> = PyDict::new(py);
    for entry in items(&plan.getattr("old_name_view_entries")?)? {
        old_names.set_item(entry.getattr("model_name")?, entry)?;
    }
    let materializations: Bound<'py, PyDict> = PyDict::new(py);
    for entry in items(&plan.getattr("model_entries")?)? {
        materializations.set_item(
            entry.getattr("name")?,
            entry.getattr("materialization_type")?.str()?,
        )?;
    }
    mapped(&plan.getattr("migration_entries")?, |entry| {
        let model: Bound<'py, PyAny> = entry.getattr("model_name")?;
        let transfer: Bound<'py, PyAny> = entry.getattr("transfer")?;
        let completed_at: Bound<'py, PyAny> = entry.getattr("completed_at")?;
        let transfer_value: Bound<'py, PyAny> = if !transfer.is_none() {
            transfer.getattr("value")?
        } else if !entry.getattr("decision")?.eq(RENAMED_DECISION)? || !completed_at.is_none() {
            py.None().into_bound(py)
        } else {
            let view: bool = materializations
                .get_item(&model)?
                .is_some_and(|kind| kind.eq(VIEW_MATERIALIZATION).unwrap_or(false));
            any(py, if view { "recreate" } else { "rebuild" })?
        };
        let old_name: Bound<'py, PyAny> = match old_names.get_item(&model)? {
            Some(old_name) => old_name_json(&old_name)?,
            None => py.None().into_bound(py),
        };
        Ok(dict(
            py,
            vec![
                ("kind", any(py, "model_migration")?),
                ("model", model.clone()),
                ("discovery", enum_value(entry, "discovery")?),
                ("decision", enum_value(entry, "decision")?),
                ("compatibility", enum_value(entry, "compatibility")?),
                (
                    "compatibility_findings",
                    list(&entry.getattr("compatibility_findings")?)?,
                ),
                ("origin_model", entry.getattr("origin_model")?),
                ("origin", relation_name(&entry.getattr("origin")?)?),
                (
                    "destination",
                    relation_name(&entry.getattr("destination")?)?,
                ),
                ("target", entry.getattr("target_name")?),
                ("origin_version_hash", entry.getattr("origin_version_hash")?),
                ("transfer", transfer_value),
                (
                    "transfer_fallback",
                    optional_enum_value(&entry.getattr("transfer_fallback")?)?,
                ),
                ("storage_transition", entry.getattr("storage_transition")?),
                (
                    "promotion",
                    optional_enum_value(&entry.getattr("promotion")?)?,
                ),
                ("completed_at", iso(&completed_at)?),
                ("old_name", old_name),
            ],
        )?
        .into_any())
    })
}

fn column_migrations_json<'py>(plan: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = plan.py();
    mapped(&plan.getattr("column_migration_entries")?, |entry| {
        Ok(dict(
            py,
            vec![
                ("kind", any(py, "column_migration")?),
                ("model", entry.getattr("model_name")?),
                ("relation", relation_name(&entry.getattr("destination")?)?),
                ("origin_column", entry.getattr("origin_column")?),
                ("destination_column", entry.getattr("destination_column")?),
                ("discovery", enum_value(entry, "discovery")?),
                ("decision", enum_value(entry, "decision")?),
                ("target", entry.getattr("target_name")?),
                ("completed_at", iso(&entry.getattr("completed_at")?)?),
            ],
        )?
        .into_any())
    })
}

fn retention_json<'py>(plan: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = plan.py();
    mapped(&plan.getattr("retention_entries")?, |entry| {
        let request: Bound<'py, PyAny> = entry.getattr("request")?;
        Ok(dict(
            py,
            vec![
                ("scope", enum_value(&request, "scope")?),
                ("database", request.getattr("database")?),
                ("schema", request.getattr("schema")?),
                ("name", request.getattr("name")?),
                ("models", entry.getattr("model_names")?),
                ("desired_days", request.getattr("desired_days")?),
                ("actual_days", entry.getattr("actual_days")?),
                ("effective_days", entry.getattr("effective_days")?),
                ("source", entry.getattr("source")?),
                ("direction", enum_value(entry, "direction")?),
                ("phase", enum_value(entry, "phase")?),
                ("statements", entry.getattr("statements")?),
                (
                    "irreversible_warning",
                    entry.getattr("irreversible_warning")?,
                ),
                ("decrease_policy", entry.getattr("decrease_policy")?),
            ],
        )?
        .into_any())
    })
}

fn table_type_json<'py>(plan: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = plan.py();
    mapped(&plan.getattr("table_type_entries")?, |entry| {
        Ok(dict(
            py,
            vec![
                ("kind", any(py, "table_type_conversion")?),
                ("model", entry.getattr("model_name")?),
                ("desired_type", entry.getattr("desired_type")?),
                ("actual_type", entry.getattr("actual_type")?),
                ("source", entry.getattr("source")?),
                ("downgrade", entry.getattr("downgrade")?),
                ("downgrade_policy", entry.getattr("downgrade_policy")?),
                (
                    "irreversible_warning",
                    entry.getattr("irreversible_warning")?,
                ),
            ],
        )?
        .into_any())
    })
}

/// The plan as one JSON document, `json.dumps(indent=2)`.
#[pyfunction]
#[pyo3(signature = (**options))]
fn format_plan_json(py: Python<'_>, options: Option<Bound<'_, PyDict>>) -> PyResult<String> {
    let arguments: KeywordArguments<'_> = KeywordArguments::read(
        py,
        "format_plan_json",
        options,
        (&["plan"], &["python_plan_entries"]),
    )?;
    let plan: Bound<'_, PyAny> = arguments.value("plan")?;
    let python_entries: Vec<Bound<'_, PyAny>> = if arguments.passed("python_plan_entries")? {
        items(&arguments.value("python_plan_entries")?)?
    } else {
        Vec::new()
    };
    let length = |field: &str| -> PyResult<usize> { plan.getattr(field)?.len() };
    let python_nodes: Vec<Bound<'_, PyAny>> = python_entries
        .iter()
        .map(python_entry_json)
        .collect::<PyResult<_>>()?;
    let result: Bound<'_, PyDict> = dict(
        py,
        vec![
            (
                "selected_count",
                any(
                    py,
                    length("model_entries")?
                        + length("seed_entries")?
                        + length("function_entries")?,
                )?,
            ),
            (
                "source_load_count",
                any(py, length("source_load_entries")?)?,
            ),
            ("python_node_count", any(py, python_nodes.len())?),
            (
                "models",
                mapped(&plan.getattr("model_entries")?, model_json)?,
            ),
            ("seeds", mapped(&plan.getattr("seed_entries")?, seed_json)?),
            (
                "source_loads",
                mapped(&plan.getattr("source_load_entries")?, source_load_json)?,
            ),
            (
                "functions",
                mapped(&plan.getattr("function_entries")?, function_json)?,
            ),
            ("python_nodes", PyList::new(py, python_nodes)?.into_any()),
            ("providers", providers_json(&plan, &python_entries)?),
            (
                "warnings",
                mapped(&plan.getattr("warnings")?, warning_json)?,
            ),
            ("retention", retention_json(&plan)?),
            ("table_type_conversions", table_type_json(&plan)?),
            ("migrations", migrations_json(&plan)?),
            ("column_migrations", column_migrations_json(&plan)?),
            (
                "old_names",
                mapped(&plan.getattr("old_name_view_entries")?, old_name_json)?,
            ),
        ],
    )?;
    let metadata: Bound<'_, PyAny> = plan.getattr("metadata")?;
    if metadata.is_truthy()? {
        result.set_item("metadata", metadata)?;
    }
    indented_json(result.as_any())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(format_plan_json, module)?)
}
