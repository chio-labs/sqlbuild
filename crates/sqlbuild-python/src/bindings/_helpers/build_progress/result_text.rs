//! Executor result objects read into the plain data build progress output renders.

use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods};
use sqlbuild_core::build_progress::models::{
    AuditResultText, BuildResultText, ErrorText, HookResultText, LifecycleEventText, LoadRowText,
    ModelResultText, NodeResultText, PythonNodeText, SkipText, TestResultText, TestStepText,
};
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, StdlibJsonOptions};
use sqlbuild_core::progress::main::format_expectation_detail::format_expectation_detail;
use sqlbuild_core::test_command::main::parameterized_test_label::parameterized_test_label;
use sqlbuild_core::test_command::models::TestParameter;

use crate::bindings::_helpers::build_progress::progress_text::expectation_step;
use crate::bindings::_helpers::plan_output::display::{cursor_bound_display, inclusive_cursor_end};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::result_output::integration_values::json_value;

const SQL_EVENT: &str = "sql";
const PRE_HOOKS: &str = "pre_hooks";
const MEASUREMENT: &str = "measurement";
const FAILED: &str = "failed";
const DECIMAL_KIND: &str = "decimal";

pub(crate) fn text(value: &Bound<'_, PyAny>, name: &str) -> PyResult<String> {
    Ok(native_field(value, name)?.str()?.to_string())
}

pub(crate) fn optional(value: &Bound<'_, PyAny>, name: &str) -> PyResult<Option<String>> {
    let field: Bound<'_, PyAny> = native_field(value, name)?;
    if field.is_none() {
        return Ok(None);
    }
    Ok(Some(field.str()?.to_string()))
}

fn texts(value: &Bound<'_, PyAny>, name: &str) -> PyResult<Vec<String>> {
    native_field(value, name)?
        .try_iter()?
        .map(|item| Ok(item?.str()?.to_string()))
        .collect()
}

fn items<'py>(value: &Bound<'py, PyAny>, name: &str) -> PyResult<Vec<Bound<'py, PyAny>>> {
    native_field(value, name)?.try_iter()?.collect()
}

fn duration(value: &Bound<'_, PyAny>) -> PyResult<Option<f64>> {
    native_field(value, "duration_ms")?.extract()
}

fn error(value: &Bound<'_, PyAny>) -> PyResult<ErrorText> {
    Ok(ErrorText {
        code: optional(value, "error_code")?,
        message: optional(value, "error_message")?,
        help: optional(value, "error_help")?,
    })
}

fn skip(value: &Bound<'_, PyAny>) -> PyResult<SkipText> {
    Ok(SkipText {
        mode: optional(value, "skip_mode")?,
        reason: optional(value, "skip_reason")?,
    })
}

fn events(value: &Bound<'_, PyAny>) -> PyResult<Vec<LifecycleEventText>> {
    let mut events: Vec<LifecycleEventText> = Vec::new();
    for event in items(value, "lifecycle_events")? {
        let content: String = native_field(&event, "content")?.extract()?;
        events.push(if text(&event, "kind")? == SQL_EVENT {
            LifecycleEventText::Sql(content)
        } else {
            LifecycleEventText::Log(content)
        });
    }
    Ok(events)
}

pub(crate) fn audit_text(audit: &Bound<'_, PyAny>) -> PyResult<AuditResultText> {
    Ok(AuditResultText {
        audit_name: text(audit, "audit_name")?,
        attached_column_name: optional(audit, "attached_column_name")?,
        attached_target_name: optional(audit, "attached_target_name")?,
        run_scope_phase: text(audit, "run_scope_phase")?,
        outcome: text(audit, "outcome")?,
        row_count: native_field(audit, "row_count")?.extract()?,
        reused: native_field(audit, "reused")?.is_truthy()?,
        executed_sql: optional(audit, "executed_sql")?,
        measurement: text(audit, "evaluation_mode")? == MEASUREMENT,
        measured_value: text(audit, "measured_value")?,
        execution_error: optional(audit, "execution_error")?,
        skip_reason: optional(audit, "skip_reason")?,
    })
}

fn audits(value: &Bound<'_, PyAny>, name: &str) -> PyResult<Vec<AuditResultText>> {
    items(value, name)?.iter().map(audit_text).collect()
}

fn hook_text(hook: &Bound<'_, PyAny>) -> PyResult<HookResultText> {
    Ok(HookResultText {
        pre_hook: text(hook, "phase")? == PRE_HOOKS,
        hook_type: text(hook, "hook_type")?,
        label: text(hook, "label")?,
        status: text(hook, "status")?,
        skip: skip(hook)?,
    })
}

fn cursor_range(model: &Bound<'_, PyAny>) -> PyResult<Option<(String, String)>> {
    let start: Bound<'_, PyAny> = native_field(model, "cursor_range_start")?;
    let end: Bound<'_, PyAny> = native_field(model, "cursor_range_end")?;
    if start.is_none()
        || end.is_none()
        || native_field(model, "empty_cursor_inputs")?.is_truthy()?
    {
        return Ok(None);
    }
    let cursor_type: Bound<'_, PyAny> = native_field(model, "cursor_type")?;
    let cursor_grain: Bound<'_, PyAny> = native_field(model, "cursor_grain")?;
    Ok(Some((
        cursor_bound_display(&start, &cursor_type, &cursor_grain)?,
        inclusive_cursor_end(&end, &cursor_type, &cursor_grain)?,
    )))
}

pub(crate) fn model_text(model: &Bound<'_, PyAny>) -> PyResult<ModelResultText> {
    Ok(ModelResultText {
        name: text(model, "model_name")?,
        status: text(model, "status")?,
        failed_phase: optional(model, "failed_phase")?,
        staging_relation: optional(model, "staging_relation")?,
        duration_ms: duration(model)?,
        batch_count: native_field(model, "batch_count")?.extract()?,
        batch_size: optional(model, "batch_size")?,
        rows_affected: native_field(model, "rows_affected")?.extract()?,
        cursor_range: cursor_range(model)?,
        empty_cursor_inputs: texts(model, "empty_cursor_inputs")?,
        waiting_on_empty_inputs: native_field(model, "waiting_on_empty_inputs")?.is_truthy()?,
        recovery_batch_count: native_field(model, "microbatch_recovery_batch_count")?.extract()?,
        synthetic_completion_count: native_field(model, "microbatch_synthetic_completion_count")?
            .extract()?,
        replay_requirement_state: optional(model, "microbatch_replay_requirement_state")?,
        audits: audits(model, "audit_results")?,
        warnings: texts(model, "warning_messages")?,
        events: events(model)?,
        hooks: items(model, "hook_results")?
            .iter()
            .map(hook_text)
            .collect::<PyResult<_>>()?,
        skip: skip(model)?,
        error: error(model)?,
    })
}

pub(crate) fn seed_text(seed: &Bound<'_, PyAny>) -> PyResult<NodeResultText> {
    Ok(NodeResultText {
        name: text(seed, "seed_name")?,
        kind: "seed".to_owned(),
        status: text(seed, "status")?,
        duration_ms: duration(seed)?,
        error: error(seed)?,
        warnings: Vec::new(),
    })
}

pub(crate) fn function_text(function: &Bound<'_, PyAny>) -> PyResult<NodeResultText> {
    Ok(NodeResultText {
        name: text(function, "function_name")?,
        kind: text(function, "function_kind")?,
        status: text(function, "status")?,
        duration_ms: duration(function)?,
        error: error(function)?,
        warnings: texts(function, "warning_messages")?,
    })
}

pub(crate) fn load_text(load: &Bound<'_, PyAny>) -> PyResult<LoadRowText> {
    Ok(LoadRowText {
        source_name: text(load, "source_name")?,
        loader_name: text(load, "loader_name")?,
        resource_kind: text(load, "resource_kind")?,
        status: text(load, "status")?,
        rows_loaded: native_field(load, "rows_loaded")?.extract()?,
        duration_ms: duration(load)?,
        events: events(load)?,
        skip: skip(load)?,
        error_message: optional(load, "error_message")?,
        warnings: texts(load, "warning_messages")?,
    })
}

pub(crate) fn test_text(test: &Bound<'_, PyAny>) -> PyResult<TestResultText> {
    let mut steps: Vec<TestStepText> = Vec::new();
    for step in items(test, "step_results")? {
        steps.push(TestStepText {
            model_name: text(&step, "model_name")?,
            outcome: text(&step, "outcome")?,
            detail: format_expectation_detail(&expectation_step(&step)?),
        });
    }
    Ok(TestResultText {
        label: test_label(test, "test_name")?,
        outcome: text(test, "outcome")?,
        steps,
        error: error(test)?,
    })
}

pub(crate) fn python_node_text(node: &Bound<'_, PyAny>) -> PyResult<PythonNodeText> {
    Ok(PythonNodeText {
        name: text(node, "node_name")?,
        kind: text(node, "kind")?,
        status: text(node, "status")?,
        error_message: optional(node, "error_message")?,
        warnings: texts(node, "warning_messages")?,
    })
}

pub(crate) fn build_text(result: &Bound<'_, PyAny>) -> PyResult<BuildResultText> {
    Ok(BuildResultText {
        failed: text(result, "status")? == FAILED,
        warning_count: native_field(result, "warning_count")?.extract()?,
        insufficient_count: native_field(result, "insufficient_count")?.extract()?,
        models: items(result, "model_results")?
            .iter()
            .map(model_text)
            .collect::<PyResult<_>>()?,
        seeds: items(result, "seed_results")?
            .iter()
            .map(seed_text)
            .collect::<PyResult<_>>()?,
        functions: items(result, "function_results")?
            .iter()
            .map(function_text)
            .collect::<PyResult<_>>()?,
        loads: items(result, "load_results")?
            .iter()
            .map(load_text)
            .collect::<PyResult<_>>()?,
        tests: items(result, "test_results")?
            .iter()
            .map(test_text)
            .collect::<PyResult<_>>()?,
        source_audits: audits(result, "source_audit_results")?,
        end_audits: audits(result, "end_audit_results")?,
    })
}

/// The label of one test or result: its name, plus source and values for parameterized cases.
pub(crate) fn test_label(item: &Bound<'_, PyAny>, name_field: &str) -> PyResult<String> {
    let name: String = native_field(item, name_field)?.extract()?;
    let source_path: Bound<'_, PyAny> = item.getattr("source_path")?;
    let values: Vec<Bound<'_, PyAny>> = native_field(item, "parameter_values")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    if source_path.is_none() || values.is_empty() {
        return Ok(name);
    }
    let mut schema: HashMap<String, Bound<'_, PyAny>> = HashMap::new();
    for declaration in item.getattr("parameter_schema")?.try_iter()? {
        let declaration: Bound<'_, PyAny> = declaration?;
        schema.insert(declaration.getattr("name")?.extract()?, declaration);
    }
    let mut parameters: Vec<TestParameter> = Vec::new();
    for pair in values {
        let (value_name, value): (String, Bound<'_, PyAny>) = pair.extract()?;
        let declaration: &Bound<'_, PyAny> = schema
            .get(&value_name)
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(value_name.clone()))?;
        let raw: Bound<'_, PyAny> = value.getattr("value")?;
        let kind: String = value.getattr("kind")?.getattr("value")?.extract()?;
        let payload: Bound<'_, PyAny> = if kind == DECIMAL_KIND {
            raw.str()?.into_any()
        } else {
            raw
        };
        parameters.push(TestParameter {
            name: value_name,
            value_type: native_field(&native_field(declaration, "value_type")?, "value")?
                .extract()?,
            nullable: declaration.getattr("nullable")?.is_truthy()?,
            rendered: compact_json(&payload)?,
        });
    }
    let path: String = source_path.call_method0("as_posix")?.extract()?;
    Ok(parameterized_test_label(&name, Some(&path), &parameters))
}

/// A payload as `json.dumps(payload, ensure_ascii=True, separators=(",", ":"))`.
fn compact_json(payload: &Bound<'_, PyAny>) -> PyResult<String> {
    let Some(value) = json_value(payload)? else {
        let options: Bound<'_, PyDict> = PyDict::new(payload.py());
        options.set_item("ensure_ascii", true)?;
        options.set_item("separators", (",", ":"))?;
        return payload
            .py()
            .import("json")?
            .call_method("dumps", (payload,), Some(&options))?
            .extract();
    };
    dumps(
        &value,
        &JsonDialect::Stdlib(StdlibJsonOptions::new(None).with_separators(",", ":")),
    )
    .map_err(|error| PyValueError::new_err(format!("{error:?}")))
}
