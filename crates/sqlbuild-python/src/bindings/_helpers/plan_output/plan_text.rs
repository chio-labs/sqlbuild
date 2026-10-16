//! The text plan: planner objects read by attribute into the native plan report.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::cli_text::main::format_plan_completion::format_plan_completion;
use sqlbuild_core::cli_text::main::format_plan_text::format_plan_text;
use sqlbuild_core::cli_text::models::{
    CliStyle, CursorPlanText, DisplayLimit, FunctionPlanText, ModelPlanText, PlanTextReport,
    PlanWarningText, ProviderUsageText, PythonPlanText, RenameHintText, SchemaFindingText,
    SeedPlanText, SourceFreshnessText, SourceLoadPlanText,
};
use sqlbuild_core::plan_display::main::format_query_diff::format_query_diff;

use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use crate::bindings::_helpers::cursor::scalars::sentinel_to_token;
use crate::bindings::_helpers::plan_output::cursor_details::{
    CursorDetails, DEFERRED, RESOLVED, cursor_details, runtime_inputs_clause,
};
use crate::bindings::_helpers::plan_output::display::{
    cursor_bound_display, format_no_input_rows, format_waiting_on_empty_inputs,
    inclusive_cursor_end, model_materialization_label,
};
use crate::bindings::_helpers::plan_output::migrations::pre_build_lines;
use crate::bindings::_helpers::plan_output::plan_json::unified_diff;
use crate::bindings::_helpers::plan_output::python_identity::{
    definition_source_text, dependency_source_text,
};
use crate::bindings::_helpers::plan_output::values::{items, optional_text, text, texts};
use crate::bindings::_helpers::records::ids::RecordId;
use crate::bindings::_helpers::records::registry;

const SKIP_ACTION: &str = "skip";
const QUERY_CHANGED: &str = "query_changed";
const CONFIG_CHANGED: &str = "config_changed";
const MICROBATCH_MODE: &str = "microbatch";
const CHANGED_IDENTITY: &str = "changed";
const PLAN_OPTIONS: (&[&str], &[&str]) = (
    &["plan"],
    &[
        "full_refresh",
        "use_color",
        "include_header",
        "display_options",
        "python_plan_entries",
        "include_direct_freshness_diagnostics",
        "include_completion",
    ],
);

/// The coloured unified diff between a previous and a current query.
pub(crate) fn query_diff(
    previous: &Bound<'_, PyAny>,
    current: &Bound<'_, PyAny>,
) -> PyResult<Vec<String>> {
    let lines = unified_diff(
        previous.py(),
        &previous.extract::<String>()?,
        &current.extract::<String>()?,
    )?;
    Ok(format_query_diff(&lines, CliStyle { use_color: true }))
}

fn token<'py>(bound: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    Ok(PyString::new(bound.py(), &sentinel_to_token(&bound)?).into_any())
}

/// `start → inclusive end` of resolved bounds, in the model's cursor display.
fn cursor_range(entry: &Bound<'_, PyAny>, bounds: &Bound<'_, PyAny>) -> PyResult<String> {
    let (cursor_type, cursor_grain) = (
        entry.getattr("cursor_type")?,
        entry.getattr("cursor_grain")?,
    );
    let start: String = cursor_bound_display(
        &token(bounds.getattr("start")?)?,
        &cursor_type,
        &cursor_grain,
    )?;
    let end: String =
        inclusive_cursor_end(&token(bounds.getattr("end")?)?, &cursor_type, &cursor_grain)?;
    Ok(format!("{start} \u{2192} {end}"))
}

fn cursor_text(entry: &Bound<'_, PyAny>, details: CursorDetails<'_>) -> PyResult<CursorPlanText> {
    let empty_inputs_window: Option<String> = if details.empty_inputs.is_truthy()? {
        Some(if details.waiting_on_empty_inputs {
            format_waiting_on_empty_inputs(&details.empty_inputs)?
        } else {
            format_no_input_rows(&details.empty_inputs)?
        })
    } else {
        None
    };
    let range: Option<String> = details
        .resolved_bounds
        .as_ref()
        .map(|bounds| cursor_range(entry, bounds))
        .transpose()?;
    Ok(CursorPlanText {
        column: optional_text(&entry.getattr("cursor_column")?)?.unwrap_or_default(),
        cursor_type: optional_text(&entry.getattr("cursor_type")?)?,
        microbatch: entry.getattr("incremental_mode")?.eq(MICROBATCH_MODE)?,
        requested_start: details.requested_start,
        requested_end: details.requested_end,
        empty_inputs_window,
        waiting_on_empty_inputs: details.waiting_on_empty_inputs,
        range,
        declared_grain: details.declared_grain,
        effective_grain: details.effective_grain,
        declared_batch_size: details.declared_batch_size,
        effective_batch_size: details.effective_batch_size,
        planned_batch_count: details.planned_batch_count,
        runtime_owned: details.runtime_owned,
        resolved: details.resolution_status == RESOLVED,
        deferred: details.resolution_status == DEFERRED,
        runtime_inputs_clause: runtime_inputs_clause(entry)?,
        batch_concurrency: text(&entry.getattr("batch_concurrency")?)?,
        unaccounted_partition_policy: optional_text(
            &entry.getattr("unaccounted_partition_policy")?,
        )?,
    })
}

/// `json.dumps(json.loads(metadata).get("config", {}), sort_keys=True, indent=2, default=str)`.
fn config_json<'py>(metadata_json: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'_> = metadata_json.py();
    let json: Bound<'_, PyModule> = py.import("json")?;
    let payload: Bound<'_, PyAny> = match json.call_method1("loads", (metadata_json,)) {
        Ok(payload) => payload,
        Err(error) if error.is_instance(py, &json.getattr("JSONDecodeError")?) => {
            return Ok(metadata_json.clone());
        }
        Err(error) => return Err(error),
    };
    let config: Bound<'_, PyAny> = match payload.downcast::<PyDict>() {
        Ok(payload) => payload
            .get_item("config")?
            .unwrap_or_else(|| PyDict::new(py).into_any()),
        Err(_) => PyDict::new(py).into_any(),
    };
    let keywords: Bound<'_, PyDict> = PyDict::new(py);
    keywords.set_item("sort_keys", true)?;
    keywords.set_item("indent", 2)?;
    keywords.set_item("default", py.import("builtins")?.getattr("str")?)?;
    json.getattr("dumps")?.call((config,), Some(&keywords))
}

fn config_diff(entry: &Bound<'_, PyAny>, reason: &str) -> PyResult<Option<Vec<String>>> {
    if !entry.getattr("config_changed")?.is_truthy()? && reason != CONFIG_CHANGED {
        return Ok(None);
    }
    let (previous, current) = (
        entry.getattr("previous_metadata_json")?,
        entry.getattr("fingerprint_metadata_json")?,
    );
    if previous.is_none() || current.is_none() {
        return Ok(None);
    }
    let (previous, current) = (config_json(&previous)?, config_json(&current)?);
    if previous.eq(&current)? {
        return Ok(None);
    }
    query_diff(&previous, &current).map(Some)
}

fn model_text(entry: &Bound<'_, PyAny>) -> PyResult<ModelPlanText> {
    let action: String = text(&entry.getattr("action")?.getattr("value")?)?;
    let reason: String = text(&entry.getattr("reason")?.getattr("value")?)?;
    let name: String = text(&entry.getattr("name")?)?;
    if action == SKIP_ACTION {
        return Ok(ModelPlanText {
            name,
            action,
            reason,
            ..ModelPlanText::default()
        });
    }
    let backfill: Bound<'_, PyAny> = entry.getattr("backfill")?;
    let mut schema_findings: Vec<SchemaFindingText> = Vec::new();
    for finding in items(&entry.getattr("schema_findings")?)? {
        schema_findings.push(SchemaFindingText {
            kind: text(&finding.getattr("kind")?.getattr("value")?)?,
            column_name: text(&finding.getattr("column_name")?)?,
            expected_type: optional_text(&finding.getattr("expected_type")?)?,
            actual_type: optional_text(&finding.getattr("actual_type")?)?,
        });
    }
    let mut rename_hints: Vec<RenameHintText> = Vec::new();
    for hint in items(&entry.getattr("column_rename_hints")?)? {
        rename_hints.push(RenameHintText {
            added_column: text(&hint.getattr("added_column")?)?,
            message: text(&hint.getattr("message")?)?,
        });
    }
    let previous_query: Bound<'_, PyAny> = entry.getattr("previous_query_sql")?;
    let query_diff_lines: Option<Vec<String>> = if previous_query.is_none()
        || (!entry.getattr("query_changed")?.is_truthy()? && reason != QUERY_CHANGED)
    {
        None
    } else {
        Some(query_diff(
            &previous_query,
            &entry.getattr("fingerprint_query_sql")?,
        )?)
    };
    Ok(ModelPlanText {
        materialization_label: model_materialization_label(entry)?,
        custom_materialization_name: optional_text(&entry.getattr("custom_materialization_name")?)?,
        backfill_action: text(&backfill.getattr("action")?.getattr("value")?)?,
        backfill_duration: optional_text(&backfill.getattr("duration")?)?,
        cursor: cursor_details(entry)?
            .map(|details| cursor_text(entry, details))
            .transpose()?,
        changed_functions: texts(&entry.getattr("changed_functions")?)?,
        schema_findings,
        rename_hints,
        config_diff: config_diff(entry, &reason)?,
        query_diff: query_diff_lines,
        name,
        action,
        reason,
    })
}

fn function_text(entry: &Bound<'_, PyAny>) -> PyResult<FunctionPlanText> {
    let reason: String = text(&entry.getattr("reason")?.getattr("value")?)?;
    let previous: Bound<'_, PyAny> = entry.getattr("previous_query_sql")?;
    let query_diff_lines: Option<Vec<String>> = if reason == QUERY_CHANGED && !previous.is_none() {
        Some(query_diff(
            &previous,
            &entry.getattr("fingerprint_query_sql")?,
        )?)
    } else {
        None
    };
    Ok(FunctionPlanText {
        name: text(&entry.getattr("name")?)?,
        kind: if entry.getattr("return_columns")?.is_truthy()? {
            "table function".to_owned()
        } else {
            format!(
                "{} udf",
                text(&entry.getattr("language")?.getattr("value")?)?
            )
        },
        reason,
        query_diff: query_diff_lines,
    })
}

fn source_load_text(entry: &Bound<'_, PyAny>) -> PyResult<SourceLoadPlanText> {
    let strategy: Bound<'_, PyAny> = entry.getattr("write_strategy")?;
    Ok(SourceLoadPlanText {
        name: text(&entry.getattr("name")?)?,
        resource_kind: text(&entry.getattr("resource_kind")?.getattr("value")?)?,
        is_reload: entry.getattr("is_reload")?.is_truthy()?,
        integration_kind: optional_text(&entry.getattr("integration_kind")?)?,
        write_strategy: if strategy.is_none() {
            None
        } else {
            Some(text(&strategy.getattr("value")?)?)
        },
        cursor_column: optional_text(&entry.getattr("cursor_column")?)?,
        unique_key: texts(&entry.getattr("unique_key")?)?,
    })
}

/// Both identity diffs of a changed Python entry, each as `format_query_diff` lines.
fn python_text(entry: &Bound<'_, PyAny>) -> PyResult<PythonPlanText> {
    let identity_status: String = text(&entry.getattr("identity_status")?.getattr("value")?)?;
    let mut diffs: [Vec<String>; 2] = [Vec::new(), Vec::new()];
    if identity_status == CHANGED_IDENTITY {
        let sources = [
            (
                definition_source_text(&entry.getattr("previous_definition_json")?)?,
                definition_source_text(&entry.getattr("current_definition_json")?)?,
            ),
            (
                dependency_source_text(&entry.getattr("previous_metadata_json")?)?,
                dependency_source_text(&entry.getattr("current_metadata_json")?)?,
            ),
        ];
        for (diff, sources) in diffs.iter_mut().zip(sources) {
            if let (Some(previous), Some(current)) = sources
                && previous != current
            {
                let py: Python<'_> = entry.py();
                *diff = query_diff(
                    &pyo3::types::PyString::new(py, &previous).into_any(),
                    &pyo3::types::PyString::new(py, &current).into_any(),
                )?;
            }
        }
    }
    let [source_diff, dependency_diff] = diffs;
    Ok(PythonPlanText {
        name: text(&entry.getattr("name")?)?,
        kind: text(&entry.getattr("kind")?.getattr("value")?)?,
        phase: text(&entry.getattr("phase")?.getattr("value")?)?,
        identity_status,
        source_diff,
        dependency_diff,
    })
}

fn provider_usages(
    plan: &Bound<'_, PyAny>,
    python_entries: &[Bound<'_, PyAny>],
) -> PyResult<Vec<ProviderUsageText>> {
    let mut usages: Vec<ProviderUsageText> = Vec::new();
    for usage in items(&plan.getattr("provider_usages")?)? {
        usages.push(ProviderUsageText {
            provider_name: text(&usage.getattr("provider_name")?)?,
            consumer_kind: text(&usage.getattr("consumer_kind")?)?,
            consumer_name: text(&usage.getattr("consumer_name")?)?,
            parameter_name: text(&usage.getattr("parameter_name")?)?,
            annotation_class_name: optional_text(&usage.getattr("annotation_class_name")?)?,
        });
    }
    for entry in python_entries {
        let (kind, name) = (
            text(&entry.getattr("kind")?.getattr("value")?)?,
            text(&entry.getattr("name")?)?,
        );
        for usage in items(&entry.getattr("provider_usages")?)? {
            usages.push(ProviderUsageText {
                provider_name: text(&usage.getattr("provider_name")?)?,
                consumer_kind: kind.clone(),
                consumer_name: name.clone(),
                parameter_name: text(&usage.getattr("parameter_name")?)?,
                annotation_class_name: optional_text(&usage.getattr("annotation_class_name")?)?,
            });
        }
    }
    Ok(usages)
}

/// `str(item)` of a metadata tuple or list, else nothing.
fn metadata_names(value: Option<Bound<'_, PyAny>>) -> PyResult<Vec<String>> {
    match value {
        Some(value) if value.is_instance_of::<PyTuple>() || value.is_instance_of::<PyList>() => {
            texts(&value)
        }
        _ => Ok(Vec::new()),
    }
}

/// The metadata `selection_diagnostics.enabled` flag, when it is a bool.
pub(crate) fn selection_diagnostics(metadata: &Bound<'_, PyAny>) -> PyResult<Option<bool>> {
    let diagnostics: Bound<'_, PyAny> = metadata.call_method1("get", ("selection_diagnostics",))?;
    let Ok(diagnostics) = diagnostics.downcast::<PyDict>() else {
        return Ok(None);
    };
    match diagnostics.get_item("enabled")? {
        Some(enabled) if enabled.is_instance_of::<pyo3::types::PyBool>() => {
            Ok(Some(enabled.is_truthy()?))
        }
        _ => Ok(None),
    }
}

fn source_freshness(metadata: &Bound<'_, PyAny>) -> PyResult<Option<SourceFreshnessText>> {
    let freshness: Bound<'_, PyAny> = metadata.call_method1("get", ("direct_source_freshness",))?;
    let Ok(freshness) = freshness.downcast::<PyDict>() else {
        return Ok(None);
    };
    let names = |key: &str| -> PyResult<Vec<String>> { metadata_names(freshness.get_item(key)?) };
    Ok(Some(SourceFreshnessText {
        observed: names("observed_source_names")?,
        changed: names("changed_source_names")?,
        unchanged: names("unchanged_source_names")?,
        unknown: names("unknown_source_names")?,
        age_warnings: names("age_warning_source_names")?,
        age_errors: names("age_error_source_names")?,
        stale_models: names("stale_model_names")?,
        blocked_models: names("blocked_model_names")?,
    }))
}

/// The names of a metadata tuple that are strings.
fn pruned_models(metadata: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    let names: Bound<'_, PyAny> = metadata.call_method1("get", ("direct_pruned_model_names",))?;
    if !names.is_instance_of::<PyTuple>() {
        return Ok(Vec::new());
    }
    let mut kept: Vec<String> = Vec::new();
    for name in items(&names)? {
        if name.is_instance_of::<pyo3::types::PyString>() {
            kept.push(name.extract()?);
        }
    }
    Ok(kept)
}

pub(crate) fn display_limit(options: &Bound<'_, PyAny>) -> PyResult<DisplayLimit> {
    Ok(DisplayLimit {
        max_entries: options.getattr("max_entries_per_section")?.extract()?,
        overflow_flag: text(&options.getattr("overflow_flag")?)?,
    })
}

fn report(arguments: &KeywordArguments<'_>) -> PyResult<PlanTextReport> {
    let py: Python<'_> = arguments.value("plan")?.py();
    let plan: Bound<'_, PyAny> = arguments.value("plan")?;
    let display_options: Bound<'_, PyAny> = {
        let given: Bound<'_, PyAny> = arguments.value("display_options")?;
        if given.is_none() {
            registry::class(py, RecordId::DisplayOptions)?.call0()?
        } else {
            given
        }
    };
    let python_entries: Vec<Bound<'_, PyAny>> = if arguments.passed("python_plan_entries")? {
        items(&arguments.value("python_plan_entries")?)?
    } else {
        Vec::new()
    };
    let flag_or = |name: &str, default: bool| -> PyResult<bool> {
        if arguments.passed(name)? {
            arguments.flag(name)
        } else {
            Ok(default)
        }
    };
    let metadata: Bound<'_, PyAny> = plan.getattr("metadata")?;
    let mut warnings: Vec<PlanWarningText> = Vec::new();
    for warning in items(&plan.getattr("warnings")?)? {
        warnings.push(PlanWarningText {
            severity: text(&warning.getattr("severity")?.getattr("value")?)?,
            message: text(&warning.getattr("message")?)?,
            model_name: optional_text(&warning.getattr("model_name")?)?,
        });
    }
    let mut seeds: Vec<SeedPlanText> = Vec::new();
    for seed in items(&plan.getattr("seed_entries")?)? {
        seeds.push(SeedPlanText {
            name: text(&seed.getattr("name")?)?,
            reason: text(&seed.getattr("reason")?)?,
        });
    }
    let pre_build: Vec<String> = pre_build_lines(Vec::new(), &plan, &display_options)?;
    Ok(PlanTextReport {
        use_color: flag_or("use_color", true)?,
        include_header: flag_or("include_header", true)?,
        full_refresh: arguments.flag("full_refresh")?,
        display: display_limit(&display_options)?,
        include_freshness_diagnostics: flag_or("include_direct_freshness_diagnostics", true)?,
        selection_diagnostics: selection_diagnostics(&metadata)?,
        models: items(&plan.getattr("model_entries")?)?
            .iter()
            .map(model_text)
            .collect::<PyResult<_>>()?,
        functions: items(&plan.getattr("function_entries")?)?
            .iter()
            .map(function_text)
            .collect::<PyResult<_>>()?,
        seeds,
        source_loads: items(&plan.getattr("source_load_entries")?)?
            .iter()
            .map(source_load_text)
            .collect::<PyResult<_>>()?,
        provider_usages: provider_usages(&plan, &python_entries)?,
        python_entries: python_entries
            .iter()
            .map(python_text)
            .collect::<PyResult<_>>()?,
        warnings,
        source_freshness: source_freshness(&metadata)?,
        remaining_stale_models: metadata_names(Some(
            metadata.call_method1("get", ("direct_remaining_stale_model_names",))?,
        ))?,
        pruned_models: pruned_models(&metadata)?,
        pre_build_lines: pre_build,
    })
}

/// The text plan grouped by reason with inline detail, optionally closed by its completion line.
#[pyfunction]
#[pyo3(signature = (**options))]
fn format_plan(py: Python<'_>, options: Option<Bound<'_, PyDict>>) -> PyResult<String> {
    let arguments: KeywordArguments<'_> =
        KeywordArguments::read(py, "format_plan", options, PLAN_OPTIONS)?;
    let report: PlanTextReport = report(&arguments)?;
    let text: String = format_plan_text(&report);
    if !arguments.flag("include_completion")? {
        return Ok(text);
    }
    Ok(format!("{text}\n\n{}", format_plan_completion(&report)))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(format_plan, module)?)
}
