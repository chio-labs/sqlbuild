//! The janitor usage check: who still reads each archive candidate, and whether to keep it.

use std::collections::{HashMap, HashSet};
use std::time::Instant;

use pyo3::IntoPyObject;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods};
use sqlbuild_host::entries::models::ExecutorHost;
use sqlbuild_model_config::model_validation::main::fixed_duration_seconds::fixed_duration_seconds;

use crate::bindings::_helpers::boundary::python_calls::{call_with, imported, within};
use crate::bindings::_helpers::janitor::janitor_keys::{Folded, Key, record, tuple};
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::records::fields::field as native_field;

const START_MESSAGE: &str = "Checking relation usage...";

/// The usage window and whether in-use candidates are kept.
pub(crate) struct UsageSettings {
    pub(crate) window: String,
    pub(crate) keep_in_use: bool,
}

/// The adapter's usage report and its usages by relation.
struct UsageOutcome<'py> {
    report: Bound<'py, PyAny>,
    usages: HashMap<Folded, Bound<'py, PyAny>>,
}

fn lifecycle(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    let options: Bound<'_, PyDict> = PyDict::new(py);
    options.set_item("operation_kind", "janitor")?;
    options.set_item("operation_name", "janitor_usage_check")?;
    host::entry(py, ExecutorHost::OperationLifecycle)?.call((), Some(&options))
}

fn replaced<'py>(
    value: &Bound<'py, PyAny>,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = value.py();
    let options: Bound<'py, PyDict> = PyDict::new(py);
    for (name, field) in fields {
        options.set_item(*name, field)?;
    }
    imported(py, "dataclasses", "replace")?.call((value,), Some(&options))
}

fn read_usage<'py>(
    (adapter, connection): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    candidates: &[Bound<'py, PyAny>],
    window_seconds: i64,
) -> PyResult<UsageOutcome<'py>> {
    let py: Python<'py> = adapter.py();
    let relations: Vec<Bound<'py, PyAny>> = candidates
        .iter()
        .map(|candidate| native_field(candidate, "relation"))
        .collect::<PyResult<_>>()?;
    let report: Bound<'py, PyAny> = call_with(
        &native_field(adapter, "relation_usage")?,
        &[
            ("connection", connection.clone()),
            ("relations", tuple(py, relations)?),
            (
                "window_seconds",
                window_seconds.into_pyobject(py)?.into_any(),
            ),
        ],
    )?;
    let mut usages: HashMap<Folded, Bound<'py, PyAny>> = HashMap::new();
    if native_field(&report, "checked")?.is_truthy()? {
        for usage in native_field(&report, "usages")?.try_iter()? {
            let usage: Bound<'py, PyAny> = usage?;
            usages.insert(Key::of(&usage)?.folded(), usage);
        }
    }
    Ok(UsageOutcome { report, usages })
}

fn completion_message(
    report: &Bound<'_, PyAny>,
    (in_use, total): (usize, usize),
    elapsed_seconds: f64,
) -> PyResult<String> {
    if !native_field(report, "checked")?.is_truthy()? {
        let reason: Option<String> = native_field(report, "reason")?.extract()?;
        return Ok(format!(
            "Relation usage not checked: {}. ({elapsed_seconds:.2}s)",
            reason.unwrap_or_default()
        ));
    }
    Ok(format!(
        "Checked relation usage: {in_use} of {total} in use. ({elapsed_seconds:.2}s)"
    ))
}

/// The plan with each candidate's reads, the usage check, and in-use candidates kept when asked.
pub(crate) fn check_janitor_usage<'py>(
    (adapter, connection): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (plan, status): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    settings: &UsageSettings,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = plan.py();
    let candidates: Vec<Bound<'py, PyAny>> = native_field(plan, "archive_candidates")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    let window_seconds: i64 = fixed_duration_seconds(&settings.window)
        .and_then(|seconds| i64::try_from(seconds).ok())
        .unwrap_or(i64::MAX);
    let started: Instant = Instant::now();
    status.call_method1("start", (START_MESSAGE,))?;
    let outcome: UsageOutcome<'py> = within(&lifecycle(py)?, |lifecycle| {
        let outcome: UsageOutcome<'py> =
            read_usage((adapter, connection), &candidates, window_seconds)?;
        let metadata: Bound<'py, PyDict> = PyDict::new(py);
        metadata.set_item("item_count", outcome.usages.len())?;
        let options: Bound<'py, PyDict> = PyDict::new(py);
        options.set_item("metadata", metadata)?;
        lifecycle.call_method("completed", (), Some(&options))?;
        Ok(outcome)
    })?;
    let checked: bool = native_field(&outcome.report, "checked")?.is_truthy()?;
    let keep: bool = checked && settings.keep_in_use;
    let mut archived: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut kept: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut kept_keys: HashSet<Folded> = HashSet::new();
    let mut in_use: usize = 0;
    for candidate in &candidates {
        let key: Folded = Key::of(&native_field(candidate, "relation")?)?.folded();
        let Some(usage) = outcome.usages.get(&key) else {
            archived.push(candidate.clone());
            continue;
        };
        in_use += 1;
        let read: Bound<'py, PyAny> = replaced(candidate, &[("usage", usage.clone())])?;
        if keep {
            kept_keys.insert(Key::of(&native_field(candidate, "key")?)?.folded());
            kept.push(read);
        } else {
            archived.push(read);
        }
    }
    let mut deletions: Vec<Bound<'py, PyAny>> = Vec::new();
    for deletion in native_field(plan, "archive_deletion_candidates")?.try_iter()? {
        let deletion: Bound<'py, PyAny> = deletion?;
        let original: Bound<'py, PyAny> = native_field(&deletion, "original_key")?;
        if original.is_none() || !kept_keys.contains(&Key::of(&original)?.folded()) {
            deletions.push(deletion);
        }
    }
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item(
        "message",
        completion_message(
            &outcome.report,
            (in_use, candidates.len()),
            started.elapsed().as_secs_f64(),
        )?,
    )?;
    options.set_item("blank_line_after", true)?;
    status.call_method("complete", (), Some(&options))?;
    let check: Bound<'py, PyAny> = record(
        py,
        ExecutorHost::JanitorUsageCheck,
        &[
            ("checked", PyBool::new(py, checked).to_owned().into_any()),
            (
                "window",
                settings.window.as_str().into_pyobject(py)?.into_any(),
            ),
            (
                "keep_in_use",
                PyBool::new(py, settings.keep_in_use).to_owned().into_any(),
            ),
            ("reason", native_field(&outcome.report, "reason")?),
        ],
    )?;
    replaced(
        plan,
        &[
            ("archive_candidates", tuple(py, archived)?),
            ("archive_deletion_candidates", tuple(py, deletions)?),
            ("kept_in_use", tuple(py, kept)?),
            ("usage_check", check),
        ],
    )
}
