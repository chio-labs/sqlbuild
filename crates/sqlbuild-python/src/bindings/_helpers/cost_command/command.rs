//! `sqb cost`: persisted run-cost history or one run's breakdown.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyInt, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::cost_command::constants::{
    DEFAULT_DETAIL_SORT, DEFAULT_HISTORY_SORT, DESCENDING_ORDER, HISTORY_SELECTOR, ISO_DATE_LENGTH,
    LATEST_SELECTOR,
};
use sqlbuild_core::cost_command::errors::CostCommandError;
use sqlbuild_core::cost_command::main::cost_history_limit::cost_history_limit;
use sqlbuild_core::cost_command::main::select_cost_run::select_cost_run;
use sqlbuild_core::cost_command::main::validate_cost_request::validate_cost_request;

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::cost_command::bounds::{parse_bound, parse_since};
use crate::bindings::_helpers::cost_command::refresh::refresh_pending_cost_run;
use crate::bindings::_helpers::cost_command::refusal::cost_error;
use crate::bindings::_helpers::cost_command::sorting::{sort_history, sort_resources};
use crate::bindings::_helpers::presentation_text::terminal::stdout_supports_color;

const NATIVE_MODULE: &str = "sqlbuild._native";

/// The request fields every cost view reads.
struct CostRequest<'py> {
    request: Bound<'py, PyAny>,
    project_dir: Bound<'py, PyAny>,
    selector: String,
    limit: Option<i64>,
    no_limit: bool,
    descending: bool,
    since: Option<String>,
    until: Option<String>,
}

impl<'py> CostRequest<'py> {
    fn read(request: &Bound<'py, PyAny>) -> PyResult<Self> {
        let py: Python<'py> = request.py();
        let requested: Bound<'py, PyAny> = request.getattr("project_dir")?;
        let order: Option<String> = request.getattr("order")?.extract()?;
        Ok(Self {
            request: request.clone(),
            project_dir: if requested.is_none() {
                imported(py, "pathlib", "Path")?.call_method0("cwd")?
            } else {
                requested
            },
            selector: request.getattr("selector")?.extract()?,
            limit: request.getattr("limit")?.extract()?,
            no_limit: request.getattr("no_limit")?.is_truthy()?,
            descending: order
                .filter(|order| !order.is_empty())
                .is_none_or(|order| order == DESCENDING_ORDER),
            since: request.getattr("since")?.extract()?,
            until: request.getattr("until")?.extract()?,
        })
    }

    fn sort_field(&self, default: &str) -> PyResult<String> {
        let sort: Option<String> = self.request.getattr("sort")?.extract()?;
        Ok(sort
            .filter(|sort| !sort.is_empty())
            .unwrap_or_else(|| default.to_owned()))
    }

    fn use_color(&self) -> PyResult<bool> {
        if self.request.getattr("no_color")?.is_truthy()? {
            return Ok(false);
        }
        stdout_supports_color(self.request.py())
    }

    /// Write the JSON file when asked, then the JSON or the rendered text to stdout.
    fn emit(&self, payload: &str, text: impl FnOnce() -> PyResult<String>) -> PyResult<()> {
        let py: Python<'py> = self.request.py();
        let path: Bound<'py, PyAny> = self.request.getattr("json_output_path")?;
        if !path.is_none() {
            let options: Bound<'py, PyDict> = PyDict::new(py);
            options.set_item("parents", true)?;
            options.set_item("exist_ok", true)?;
            path.getattr("parent")?
                .call_method("mkdir", (), Some(&options))?;
            let encoding: Bound<'py, PyDict> = PyDict::new(py);
            encoding.set_item("encoding", "utf-8")?;
            path.call_method("write_text", (format!("{payload}\n"),), Some(&encoding))?;
        }
        let rendered: String = if self.request.getattr("json_output")?.is_truthy()? {
            payload.to_owned()
        } else {
            text()?
        };
        py.import("sys")?
            .getattr("stdout")?
            .call_method1("write", (PyString::new(py, &format!("{rendered}\n")),))?;
        Ok(())
    }
}

fn refused(py: Python<'_>, result: Result<(), CostCommandError>) -> PyResult<()> {
    result.map_err(|error| cost_error(py, &error))
}

fn cost_runs<'py>(request: &CostRequest<'py>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py: Python<'py> = request.request.py();
    call_with(
        &imported(py, NATIVE_MODULE, "list_cost_runs")?,
        &[("project_dir", request.project_dir.clone())],
    )?
    .try_iter()?
    .collect()
}

/// Whether the record completed inside the `--since`/`--until` window.
fn in_window(
    record: &Bound<'_, PyAny>,
    since: Option<&Bound<'_, PyAny>>,
    (until, until_is_date): (Option<&Bound<'_, PyAny>>, bool),
) -> PyResult<bool> {
    let completed: Bound<'_, PyAny> = record.getattr("completed_at")?;
    if let Some(since) = since
        && !completed.ge(since)?
    {
        return Ok(false);
    }
    match until {
        Some(until) if until_is_date => completed.lt(until),
        Some(until) => completed.le(until),
        None => Ok(true),
    }
}

fn run_history(request: &CostRequest<'_>) -> PyResult<i32> {
    let py: Python<'_> = request.request.py();
    let sort_field: String = request.sort_field(DEFAULT_HISTORY_SORT)?;
    refused(
        py,
        validate_cost_request(
            &request.selector,
            (request.limit, request.no_limit),
            &sort_field,
            request.since.is_some() || request.until.is_some(),
        ),
    )?;
    let since: Option<Bound<'_, PyAny>> = request
        .since
        .as_deref()
        .map(|value| parse_since(py, value))
        .transpose()?;
    let until: Option<Bound<'_, PyAny>> = request
        .until
        .as_deref()
        .map(|value| parse_bound(py, value, "--until", true))
        .transpose()?;
    if let (Some(since), Some(until)) = (&since, &until)
        && since.gt(until)?
    {
        return Err(cost_error(
            py,
            &CostCommandError::new("C711", "cost --since must not be after --until"),
        ));
    }
    let until_is_date: bool = request
        .until
        .as_deref()
        .is_some_and(|value| value.chars().count() == ISO_DATE_LENGTH);
    let mut matching: Vec<Bound<'_, PyAny>> = Vec::new();
    for record in cost_runs(request)? {
        if in_window(&record, since.as_ref(), (until.as_ref(), until_is_date))? {
            matching.push(record);
        }
    }
    let matching_count: usize = matching.len();
    let mut records: Vec<Bound<'_, PyAny>> =
        sort_history(py, matching, &sort_field, request.descending)?;
    if let Some(limit) = cost_history_limit(request.limit, request.no_limit) {
        records.truncate(usize::try_from(limit).unwrap_or(0));
    }
    let records: Bound<'_, PyAny> = PyTuple::new(py, records)?.into_any();
    let count: Bound<'_, PyAny> = PyInt::new(py, matching_count).into_any();
    let payload: String = call_with(
        &imported(py, NATIVE_MODULE, "format_cost_history_json")?,
        &[
            ("records", records.clone()),
            ("matching_count", count.clone()),
        ],
    )?
    .extract()?;
    request.emit(&payload, || {
        call_with(
            &imported(py, NATIVE_MODULE, "format_cost_history")?,
            &[
                ("records", records),
                ("matching_count", count),
                (
                    "use_color",
                    PyBool::new(py, request.use_color()?).to_owned().into_any(),
                ),
            ],
        )?
        .extract()
    })?;
    Ok(0)
}

/// The persisted run the selector names.
fn resolve_run<'py>(request: &CostRequest<'py>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.request.py();
    let records: Vec<Bound<'py, PyAny>> = cost_runs(request)?;
    if request.selector == LATEST_SELECTOR {
        let latest: Bound<'py, PyAny> = call_with(
            &imported(py, NATIVE_MODULE, "resolve_cost_run")?,
            &[
                ("project_dir", request.project_dir.clone()),
                ("selector", PyString::new(py, &request.selector).into_any()),
            ],
        )?;
        if latest.is_none() {
            return Err(cost_error(
                py,
                &CostCommandError::new("C704", "No persisted SQLBuild cost runs were found"),
            ));
        }
        return Ok(latest);
    }
    let run_ids: Vec<String> = records
        .iter()
        .map(|record| record.getattr("run_id")?.extract())
        .collect::<PyResult<_>>()?;
    let index: usize =
        select_cost_run(&run_ids, &request.selector).map_err(|error| cost_error(py, &error))?;
    Ok(records[index].clone())
}

/// `dataclasses.replace(record, cost=replace(record.cost, resources=resources))`.
fn with_resources<'py>(
    record: &Bound<'py, PyAny>,
    resources: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = record.py();
    let replace: Bound<'py, PyAny> = imported(py, "dataclasses", "replace")?;
    let cost_changes: Bound<'py, PyDict> = PyDict::new(py);
    cost_changes.set_item("resources", PyTuple::new(py, resources)?)?;
    let cost: Bound<'py, PyAny> = replace.call((record.getattr("cost")?,), Some(&cost_changes))?;
    let changes: Bound<'py, PyDict> = PyDict::new(py);
    changes.set_item("cost", cost)?;
    replace.call((record,), Some(&changes))
}

fn run_detail(request: &CostRequest<'_>) -> PyResult<i32> {
    let py: Python<'_> = request.request.py();
    let sort_field: String = request.sort_field(DEFAULT_DETAIL_SORT)?;
    refused(
        py,
        validate_cost_request(
            &request.selector,
            (request.limit, request.no_limit),
            &sort_field,
            request.since.is_some() || request.until.is_some(),
        ),
    )?;
    let record: Bound<'_, PyAny> = resolve_run(request)?;
    let resources: Vec<Bound<'_, PyAny>> = record
        .getattr("cost")?
        .getattr("resources")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    let resources: Vec<Bound<'_, PyAny>> =
        sort_resources(py, resources, &sort_field, request.descending)?;
    let record: Bound<'_, PyAny> = with_resources(&record, &resources)?;
    let limit: Option<i64> = if request.no_limit {
        None
    } else {
        request.limit
    };
    let json_record: Bound<'_, PyAny> = match limit {
        Some(limit) => {
            let kept: usize = usize::try_from(limit).unwrap_or(0).min(resources.len());
            with_resources(&record, &resources[..kept])?
        }
        None => record.clone(),
    };
    let payload: String = imported(py, NATIVE_MODULE, "format_cost_json")?
        .call1((json_record,))?
        .extract()?;
    request.emit(&payload, || {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("record", &record)?;
        options.set_item("use_color", request.use_color()?)?;
        options.set_item("limit", limit)?;
        imported(py, NATIVE_MODULE, "format_cost_breakdown")?
            .call((), Some(&options))?
            .extract()
    })?;
    Ok(0)
}

/// Render persisted cost history or one run breakdown, without the delayed refresh.
fn report(request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let request: CostRequest<'_> = CostRequest::read(request)?;
    if request.selector == HISTORY_SELECTOR {
        return run_history(&request);
    }
    run_detail(&request)
}

/// Refresh a delayed run, then render persisted cost history or one run breakdown.
#[pyfunction]
fn run_cost_command(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<i32> {
    refresh_pending_cost_run(py, request);
    report(request)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_cost_command, module)?)?;
    Ok(())
}
