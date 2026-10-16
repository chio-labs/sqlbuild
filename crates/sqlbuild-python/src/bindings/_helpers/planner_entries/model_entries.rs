//! Per-model plan entries from resolved change results and warehouse snapshot facts.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, imported, keywords,
};
use crate::bindings::_helpers::planner_entries::values::{
    COMPILE_TYPES, MICROBATCH_CONCURRENCY_MESSAGE, boolean, error_of, native, none, planner_type,
    replaced, string,
};
use crate::bindings::_helpers::planner_phases::full_refresh::resolve_model_full_refresh;
use crate::bindings::_helpers::planner_resolution::cursor_ranges::{
    CursorWindowInputs, config_str, cursor_safety_configs, empty_cursor_inputs, microbatch_range,
    model_cursor_overrides, plan_cursor_bounds,
};
use crate::bindings::_helpers::planner_resolution::cursor_warnings::with_cursor_safety_warnings;
use crate::bindings::_helpers::planner_resolution::orchestration::{
    resolve_model_hook_entries, resolve_model_sql,
};
use crate::bindings::_helpers::planner_strategy::microbatch_limits::apply_configured_microbatch_limits;
use crate::bindings::_helpers::planner_strategy::model_entries::assemble_model_plan_entry;
use crate::bindings::_helpers::planner_strategy::strategy::resolve_model_plan_action;
use crate::bindings::_helpers::records::ids::{ErrorId, NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

const MICROBATCH_COMPLEXITY_CODE: &str = "MICROBATCH_CONCURRENCY_COMPLEXITY";

/// One model's planning request after change detection.
struct ModelPlanRequest<'py> {
    model: Bound<'py, PyAny>,
    snapshot: Bound<'py, PyAny>,
    adapter: Bound<'py, PyAny>,
    context: Bound<'py, PyAny>,
    sql_analysis_enabled: Bound<'py, PyAny>,
    full_refresh: bool,
    overrides: (Bound<'py, PyAny>, Bound<'py, PyAny>),
    change_result: Bound<'py, PyAny>,
    external_resolver: Bound<'py, PyAny>,
    protect_full_refresh: bool,
}

/// Build a model plan entry and its warnings from a resolved change result.
fn plan_model_from_change<'py>(
    request: &ModelPlanRequest<'py>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let model = &request.model;
    let context = &request.context;
    let py = model.py();
    let full_refresh = boolean(py, request.full_refresh)?;
    let backfill = if request.full_refresh {
        native(
            py,
            RecordId::BackfillResult,
            &[(
                "action",
                planner_type(py, RecordId::BackfillAction, "FULL")?,
            )],
        )?
    } else {
        request.change_result.getattr("backfill")?
    };
    let cursor_column = config_str(model, "cursor")?;
    native(
        py,
        NativeAttr::ValidateSourceCursorInputColumns,
        &[
            ("model", model.clone()),
            ("cursor_column", cursor_column.clone()),
            ("models_by_name", context.getattr("models_by_name")?),
            ("functions_by_name", context.getattr("functions_by_name")?),
            ("source_map", context.getattr("source_map")?),
            (
                "source_warehouse_columns",
                context.getattr("source_warehouse_columns")?,
            ),
        ],
    )?;
    let resolved = resolve_model_plan_action(model, &request.change_result, request.full_refresh)?;
    let (action, reason) = (resolved.get_item(0)?, resolved.get_item(1)?);
    let materialization_type = native(
        py,
        NativeAttr::GetMaterializationType,
        &[("model", model.clone())],
    )?;
    let replaces_relation = native(
        py,
        NativeAttr::ReplacesIncrementalRelation,
        &[
            ("materialization_type", materialization_type.clone()),
            ("action", action.clone()),
        ],
    )?
    .is_truthy()?;
    let full_rebuild_cause = if replaces_relation {
        native(
            py,
            NativeAttr::DescribeFullRebuildCause,
            &[
                ("change_result", request.change_result.clone()),
                ("full_refresh", full_refresh.clone()),
            ],
        )?
    } else {
        none(py)
    };
    if !full_rebuild_cause.is_none() && request.protect_full_refresh && !request.full_refresh {
        native(
            py,
            NativeAttr::CheckFullRebuildAllowed,
            &[
                ("model", model.clone()),
                ("change_result", request.change_result.clone()),
                ("full_rebuild_cause", full_rebuild_cause.clone()),
            ],
        )?;
    }
    let pair = native(
        py,
        RecordId::CursorOverridePair,
        &[
            ("start_cursor_override", request.overrides.0.clone()),
            ("end_cursor_override", request.overrides.1.clone()),
        ],
    )?;
    let resolved_sql = resolve_model_sql(
        py,
        Some(keywords(
            py,
            &[
                ("adapter", request.adapter.clone()),
                ("model", model.clone()),
                ("snapshot", request.snapshot.clone()),
                ("context", context.clone()),
                ("backfill", backfill.clone()),
                ("full_refresh", full_refresh.clone()),
                ("cursor_overrides", pair),
                (
                    "external_sql_reference_resolver",
                    request.external_resolver.clone(),
                ),
                ("replaces_relation", boolean(py, replaces_relation)?),
                ("full_rebuild_cause", full_rebuild_cause),
            ],
        )?),
    )?;
    let hooks = resolve_model_hook_entries(
        model,
        request.adapter.clone(),
        context.clone(),
        request.external_resolver.clone(),
    )?;
    let (future_config, start_config) = cursor_safety_configs(model, context)?;
    native(
        py,
        NativeAttr::ValidateCappedWatermarkInputs,
        &[
            ("model", model.clone()),
            ("models_by_name", context.getattr("models_by_name")?),
            ("functions_by_name", context.getattr("functions_by_name")?),
        ],
    )?;
    let cursor_input_relations = native(
        py,
        NativeAttr::BuildCursorInputRelations,
        &[
            ("model", model.clone()),
            ("adapter", request.adapter.clone()),
            ("model_locations", context.getattr("model_locations")?),
            ("models_by_name", context.getattr("models_by_name")?),
            ("functions_by_name", context.getattr("functions_by_name")?),
            ("seed_locations", context.getattr("seed_locations")?),
            ("source_map", context.getattr("source_map")?),
            ("cursor_column", cursor_column.clone()),
            (
                "runtime_cursor_producer_names",
                context.getattr("runtime_cursor_producer_names")?,
            ),
        ],
    )?;
    let mut any_runtime_owned = false;
    for relation in cursor_input_relations.try_iter()? {
        if relation?.getattr("is_runtime_owned")?.is_truthy()? {
            any_runtime_owned = true;
            break;
        }
    }
    let complete_override = !request.overrides.0.is_none() && !request.overrides.1.is_none();
    let runtime_owned = any_runtime_owned && !complete_override;
    let window = CursorWindowInputs {
        snapshot: request.snapshot.clone(),
        backfill: backfill.clone(),
        overrides: request.overrides.clone(),
        runtime_owned,
        policies: (future_config.clone(), start_config.clone()),
        invocation_time: context.getattr("invocation_time")?,
        full_refresh: request.full_refresh,
        replaces_relation,
        cursor_input_relations: cursor_input_relations.clone(),
    };
    let cursor_bounds = plan_cursor_bounds(model, &window)?;
    let (empty_inputs, waiting_on_empty_inputs) = empty_cursor_inputs(model, &window)?;
    let range = microbatch_range(model, &window)?;
    let assembled = assemble_model_plan_entry(Some(&keywords(
        py,
        &[
            ("model", model.clone()),
            ("adapter", request.adapter.clone()),
            ("snapshot", request.snapshot.clone()),
            ("change_result", request.change_result.clone()),
            ("action", action),
            ("reason", reason),
            ("materialization_type", materialization_type),
            ("resolved_sql", resolved_sql),
            ("sql_analysis_enabled", request.sql_analysis_enabled.clone()),
            ("pre_hooks", hooks.get_item(0)?),
            ("post_hooks", hooks.get_item(1)?),
            ("cursor_column", cursor_column),
            ("cursor_input_relations", cursor_input_relations),
            ("runtime_owned_cursor_bounds", boolean(py, runtime_owned)?),
            ("cursor_bounds", cursor_bounds.clone()),
            ("microbatch_range", range.clone()),
            ("empty_cursor_inputs", empty_inputs),
            (
                "waiting_on_empty_inputs",
                boolean(py, waiting_on_empty_inputs)?,
            ),
            ("backfill", backfill),
            ("start_cursor_override", request.overrides.0.clone()),
            ("end_cursor_override", request.overrides.1.clone()),
            ("future_cursor_config", future_config),
            ("start_cursor_config", start_config),
            ("invocation_time", context.getattr("invocation_time")?),
        ],
    )?))?;
    let bounds = if range.is_truthy()? {
        range
    } else {
        cursor_bounds
    };
    let warnings = with_cursor_safety_warnings(
        &assembled.get_item(1)?,
        &model_reads::name_object(model)?,
        &bounds,
    )?;
    Ok((assembled.get_item(0)?, warnings))
}

/// The binding-diagnostic failure that stops planning, if any diagnostic is an error.
fn check_binding_diagnostics<'py>(
    project: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
    relations: &Bound<'py, PyAny>,
    selected_keys: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let py = project.py();
    let sql_test = imported(py, COMPILE_TYPES, "CompiledResourceType")?.getattr("SQL_TEST")?;
    let mut errors: Vec<Bound<'py, PyAny>> = Vec::new();
    for diagnostic in project.getattr("diagnostics")?.try_iter()? {
        let diagnostic = diagnostic?;
        if diagnostic.getattr("is_error")?.is_truthy()?
            && diagnostic.getattr("resource_type")?.ne(&sql_test)?
        {
            errors.push(diagnostic);
        }
    }
    let bound = native(
        py,
        NativeAttr::SourceBindingDiagnostics,
        &[
            ("project", project.clone()),
            ("columns", relations.getattr("source_warehouse_columns")?),
            (
                "profile",
                adapter.call_method0("expression_inference_profile")?,
            ),
            ("selected_keys", selected_keys.clone()),
        ],
    )?;
    for diagnostic in bound.try_iter()? {
        let diagnostic = diagnostic?;
        if diagnostic.getattr("is_error")?.is_truthy()? {
            errors.push(diagnostic);
        }
    }
    let Some(first) = errors.first() else {
        return Ok(());
    };
    let mut lines: Vec<String> = Vec::new();
    for diagnostic in &errors {
        let position = |field: &str| -> PyResult<String> {
            let value = diagnostic.getattr(field)?;
            Ok(if value.is_truthy()? {
                value.str()?.to_string()
            } else {
                "1".to_owned()
            })
        };
        lines.push(format!(
            "error[{}]: {}\n  --> {}:{}:{}",
            diagnostic.getattr("code")?.str()?,
            diagnostic.getattr("message")?.str()?,
            diagnostic.getattr("path")?.str()?,
            position("line")?,
            position("column")?,
        ));
    }
    Err(error_of(
        py,
        ErrorId::PlannerInput,
        &lines.join("\n"),
        &[("code", first.getattr("code")?)],
    ))
}

fn names_of(entries: &[Bound<'_, PyAny>]) -> PyResult<String> {
    Ok(entries
        .iter()
        .map(|entry| Ok(entry.getattr("name")?.str()?.to_string()))
        .collect::<PyResult<Vec<String>>>()?
        .join(", "))
}

/// Concurrent microbatch configuration checks, and the warning concurrency complexity earns.
fn check_microbatch_concurrency<'py>(
    project: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
    entries: &[Bound<'py, PyAny>],
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let py = project.py();
    let skip = planner_type(py, RecordId::PlanAction, "SKIP")?;
    let create = planner_type(py, RecordId::PlanAction, "CREATE_TABLE")?;
    let mut configured: Vec<Bound<'py, PyAny>> = Vec::new();
    for entry in entries {
        if entry.getattr("batch_concurrency")?.gt(1)? && entry.getattr("action")?.ne(&skip)? {
            configured.push(entry.clone());
        }
    }
    let settings = project.getattr("settings")?;
    if !configured.is_empty() && !settings.getattr("microbatch_concurrency")?.is_truthy()? {
        let guidance = native(py, NativeAttr::MicrobatchGuidance, &[])?;
        let prefix: &str = MICROBATCH_CONCURRENCY_MESSAGE;
        return Err(error_of(
            py,
            ErrorId::CompileInput,
            &format!(
                "{prefix}{}; {}",
                names_of(&configured)?,
                guidance.get_item(0)?.str()?
            ),
            &[("help", guidance.get_item(1)?)],
        ));
    }
    if !configured.is_empty()
        && !adapter
            .call_method0("supports_concurrent_microbatch_dml")?
            .is_truthy()?
    {
        return Err(error_of(
            py,
            ErrorId::CompileInput,
            &format!(
                "adapter '{}' does not support concurrent microbatch delete/insert DML; set \
                 batch_concurrency = 1",
                adapter.getattr("adapter_name")?.str()?
            ),
            &[],
        ));
    }
    let mut concurrent: Vec<Bound<'py, PyAny>> = Vec::new();
    for entry in configured {
        if entry.getattr("action")?.ne(&create)? {
            concurrent.push(entry);
        }
    }
    if concurrent.is_empty() || !settings.getattr("concurrency")?.gt(1)? {
        return Ok(None);
    }
    let count = concurrent.len();
    native(
        py,
        RecordId::PlanWarning,
        &[
            ("model_name", none(py)),
            (
                "severity",
                registry::class(py, RecordId::WarningSeverity)?.getattr("WARNING")?,
            ),
            ("code", string(py, MICROBATCH_COMPLEXITY_CODE)),
            (
                "message",
                string(
                    py,
                    &format!(
                        "Concurrent microbatch execution is enabled for {count} selected \
                             model{}: {}. Concurrent batches may complete out of order and rely \
                             on persistent microbatch history for gap recovery and fingerprint \
                             provenance. State deletion or corruption can require synthetic \
                             reconciliation and weaken version guarantees. Keep \
                             batch_concurrency at 1 unless the runtime benefit justifies this \
                             complexity; see the microbatch concurrency and recovery \
                             documentation.",
                        if count == 1 { "" } else { "s" },
                        names_of(&concurrent)?
                    ),
                ),
            ),
        ],
    )
    .map(Some)
}

/// Build model plan entries from snapshot and per-model resolved actions.
fn plan_entries<'py>(args: &KeywordArguments<'py>) -> PyResult<Bound<'py, PyAny>> {
    let project = args.value("project")?;
    let py = project.py();
    let adapter = args.value("adapter")?;
    let scope = args.value("scope")?;
    let snapshot = args.value("snapshot")?;
    let relations = args.value("relations")?;
    let models = args.value("resolved_actions")?.getattr("models")?;
    let cursor_overrides = args.value("cursor_overrides")?;
    let full_refresh = args.value("full_refresh")?;
    let inputs = args.value("build_inputs")?;
    let inputs = if inputs.is_none() {
        native(py, RecordId::PlanEntryBuildInputs, &[])?
    } else {
        inputs
    };
    let selected_keys = scope.getattr("selected_keys")?;
    check_binding_diagnostics(&project, &adapter, &relations, &selected_keys)?;
    let freshness_blocked = inputs.getattr("source_freshness_blocked_model_names")?;
    let external_blocked = inputs.getattr("external_blocked_model_names")?;
    let start_override = inputs.getattr("start_cursor_override")?;
    let end_override = inputs.getattr("end_cursor_override")?;
    let producers = native(
        py,
        NativeAttr::RuntimeCursorProducerNames,
        &[
            ("scope", scope.clone()),
            ("source_map", relations.getattr("source_map")?),
        ],
    )?;
    let functions_by_name = PyDict::new(py);
    for function in project.getattr("functions")?.try_iter()? {
        let function = function?;
        functions_by_name.set_item(function.getattr("name")?, function)?;
    }
    let settings = project.getattr("settings")?;
    let models_by_name = scope.getattr("models_by_name")?;
    let context = native(
        py,
        RecordId::ModelPlanContext,
        &[
            ("model_locations", relations.getattr("model_locations")?),
            ("models_by_name", models_by_name.clone()),
            ("functions_by_name", functions_by_name.into_any()),
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
            ("runtime_cursor_producer_names", producers),
            (
                "future_cursor_config",
                inputs.getattr("future_cursor_config")?,
            ),
            (
                "start_cursor_config",
                inputs.getattr("start_cursor_config")?,
            ),
            ("invocation_time", inputs.getattr("invocation_time")?),
        ],
    )?;
    let skip = planner_type(py, RecordId::PlanAction, "SKIP")?;
    let microbatch = registry::class(py, RecordId::IncrementalMode)?.getattr("MICROBATCH")?;
    let mut entries: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut warnings: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in scope.getattr("execution_order")?.try_iter()? {
        let key = key?;
        let name = key.getattr("name")?;
        if !selected_keys.contains(&key)? || !models.contains(&name)? {
            continue;
        }
        let model = models_by_name.call_method1("get", (&name,))?;
        let resolved = models.get_item(&name)?;
        if model.is_none() {
            continue;
        }
        let overrides = model_cursor_overrides(
            &model,
            &cursor_overrides,
            (start_override.clone(), end_override.clone()),
        )?;
        let effective_full_refresh = resolve_model_full_refresh(&model, full_refresh.is_truthy()?)?;
        let (mut entry, entry_warnings) = plan_model_from_change(&ModelPlanRequest {
            model: model.clone(),
            snapshot: snapshot.clone(),
            adapter: adapter.clone(),
            context: context.clone(),
            sql_analysis_enabled: settings.getattr("sql_analysis")?,
            full_refresh: effective_full_refresh,
            overrides,
            change_result: resolved.getattr("change")?,
            external_resolver: project.getattr("external_sql_reference_resolver")?,
            protect_full_refresh: !freshness_blocked.contains(&name)?
                && !external_blocked.contains(&name)?,
        })?;
        let entry_name = entry.getattr("name")?;
        if freshness_blocked.contains(&entry_name)? {
            entry = replaced(
                &entry,
                &[
                    ("action", skip.clone()),
                    (
                        "reason",
                        planner_type(py, RecordId::PlanReason, "SOURCE_FRESHNESS_ERROR")?,
                    ),
                ],
            )?;
        }
        if external_blocked.contains(&entry_name)? {
            entry = replaced(
                &entry,
                &[
                    ("action", skip.clone()),
                    (
                        "reason",
                        planner_type(py, RecordId::PlanReason, "EXTERNAL_UPSTREAM_FAILED")?,
                    ),
                ],
            )?;
        }
        if entry.getattr("incremental_mode")?.eq(&microbatch)? {
            let policy = entry.getattr("unaccounted_partition_policy")?;
            let policy = if policy.is_truthy()? {
                policy
            } else {
                settings.getattr("microbatch_unaccounted_partition_policy")?
            };
            entry = replaced(&entry, &[("unaccounted_partition_policy", policy)])?;
            if entry.getattr("action")?.ne(&skip)? {
                let limited = apply_configured_microbatch_limits(&entry, &inputs)?;
                entry = limited.get_item(0)?;
                for warning in limited.get_item(1)?.try_iter()? {
                    warnings.push(warning?);
                }
            }
        }
        entries.push(entry);
        for warning in entry_warnings.try_iter()? {
            warnings.push(warning?);
        }
    }
    if let Some(warning) = check_microbatch_concurrency(&project, &adapter, &entries)? {
        warnings.push(warning);
    }
    native(
        py,
        RecordId::PlannerModelEntryResults,
        &[
            ("entries", PyTuple::new(py, entries)?.into_any()),
            ("warnings", PyTuple::new(py, warnings)?.into_any()),
        ],
    )
}

/// Build model plan entries from snapshot and per-model resolved actions.
#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn build_plan_entries<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "build_plan_entries",
        kwargs,
        (
            &[
                "project",
                "adapter",
                "scope",
                "snapshot",
                "relations",
                "resolved_actions",
                "cursor_overrides",
                "full_refresh",
            ],
            &["build_inputs"],
        ),
    )?;
    plan_entries(&args)
}

/// Detect changes and build a plan entry and warnings for a single model.
#[pyfunction]
#[pyo3(signature = (**kwargs))]
fn plan_model<'py>(
    py: Python<'py>,
    kwargs: Option<Bound<'py, PyDict>>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let args = KeywordArguments::read(
        py,
        "plan_model",
        kwargs,
        (
            &[
                "model",
                "snapshot",
                "adapter",
                "context",
                "sql_analysis_enabled",
                "query_change_tracking",
                "full_refresh",
                "cursor_overrides",
            ],
            &["external_sql_reference_resolver"],
        ),
    )?;
    let model = args.value("model")?;
    let snapshot = args.value("snapshot")?;
    let change_result = native(
        py,
        NativeAttr::DetectModelChanges,
        &[
            ("model", model.clone()),
            ("snapshot", snapshot.clone()),
            ("sql_analysis_enabled", args.value("sql_analysis_enabled")?),
            (
                "query_change_tracking",
                args.value("query_change_tracking")?,
            ),
            ("full_refresh", args.value("full_refresh")?),
        ],
    )?;
    let overrides = args.value("cursor_overrides")?;
    plan_model_from_change(&ModelPlanRequest {
        model,
        snapshot,
        adapter: args.value("adapter")?,
        context: args.value("context")?,
        sql_analysis_enabled: args.value("sql_analysis_enabled")?,
        full_refresh: args.flag("full_refresh")?,
        overrides: (
            overrides.getattr("start_cursor_override")?,
            overrides.getattr("end_cursor_override")?,
        ),
        change_result,
        external_resolver: args.value("external_sql_reference_resolver")?,
        protect_full_refresh: true,
    })
}

/// Build a name-to-materialization-type lookup from planned model entries.
#[pyfunction]
#[pyo3(signature = (model_entries, /))]
fn build_model_materializations<'py>(
    model_entries: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let lookup = PyDict::new(model_entries.py());
    for entry in model_entries.try_iter()? {
        let entry = entry?;
        lookup.set_item(
            entry.getattr("name")?,
            entry.getattr("materialization_type")?,
        )?;
    }
    Ok(lookup)
}

/// Check if any scope dependency is in the selected keys.
#[pyfunction]
#[pyo3(signature = (*, scope_deps, selected_keys))]
pub(crate) fn scope_overlaps(
    scope_deps: &Bound<'_, PyAny>,
    selected_keys: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    for dependency in scope_deps.try_iter()? {
        if selected_keys.contains(dependency?)? {
            return Ok(true);
        }
    }
    Ok(false)
}

pub(super) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_plan_entries, module)?)?;
    module.add_function(wrap_pyfunction!(plan_model, module)?)?;
    module.add_function(wrap_pyfunction!(build_model_materializations, module)?)?;
    module.add_function(wrap_pyfunction!(scope_overlaps, module)?)
}
