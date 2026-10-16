//! `sqb seed`: compile the selected seeds, load them, and report.

use std::collections::HashMap;
use std::time::Instant;

use pyo3::exceptions::PyKeyError;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyInt, PyString, PyTuple};
use pyo3::{pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_core::seed_command::main::render_seed_completion::render_seed_completion;
use sqlbuild_core::seed_command::main::render_seed_ready::render_seed_ready;
use sqlbuild_core::seed_command::main::render_seed_row::render_seed_row;
use sqlbuild_core::seed_command::main::seed_exit_code::seed_exit_code;
use sqlbuild_core::seed_command::models::SeedRow;

use crate::bindings::_helpers::command_runtime::invocation::resolve_command_invocation;
use crate::bindings::_helpers::compile_driver::plan_result::connection_with_hooks;
use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;

const SUCCESS_STATUS: &str = "success";
const FAILED_STATUS: &str = "failed";
const EXECUTION_COMMAND: &str = "sqb seed";

fn text<'py>(py: Python<'py>, value: &str) -> Bound<'py, PyAny> {
    PyString::new(py, value).into_any()
}

fn status_value(result: &Bound<'_, PyAny>) -> PyResult<String> {
    result.getattr("status")?.getattr("value")?.extract()
}

/// Forward positional connection timing to a reporter that takes keywords.
#[pyclass(module = "sqlbuild._native", frozen)]
struct SeedConnectionRelay {
    reporter: Py<PyAny>,
}

#[pymethods]
impl SeedConnectionRelay {
    fn on_connection_complete(
        &self,
        py: Python<'_>,
        connection_count: i64,
        elapsed_seconds: f64,
    ) -> PyResult<()> {
        self.forward(
            py,
            "on_connection_complete",
            (connection_count, elapsed_seconds),
        )
    }

    fn on_connection_error(
        &self,
        py: Python<'_>,
        connection_count: i64,
        elapsed_seconds: f64,
    ) -> PyResult<()> {
        self.forward(
            py,
            "on_connection_error",
            (connection_count, elapsed_seconds),
        )
    }
}

impl SeedConnectionRelay {
    fn forward(
        &self,
        py: Python<'_>,
        method: &str,
        (connection_count, elapsed_seconds): (i64, f64),
    ) -> PyResult<()> {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("connection_count", connection_count)?;
        options.set_item("elapsed_seconds", elapsed_seconds)?;
        self.reporter
            .bind(py)
            .call_method(method, (), Some(&options))?;
        Ok(())
    }
}

fn connection_relay<'py>(
    reporter: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, SeedConnectionRelay>> {
    Bound::new(
        reporter.py(),
        SeedConnectionRelay {
            reporter: reporter.clone().unbind(),
        },
    )
}

/// Write each finished seed's row and its execution event.
#[pyclass(module = "sqlbuild._native", frozen)]
struct SeedCompletionRelay {
    stream: Py<PyAny>,
    use_color: bool,
    ordinals: HashMap<String, usize>,
    total: usize,
    event_writer: Py<PyAny>,
    plan: Py<PyAny>,
    projector: Option<Py<PyAny>>,
}

#[pymethods]
impl SeedCompletionRelay {
    fn on_seed_complete(&self, py: Python<'_>, result: Bound<'_, PyAny>) -> PyResult<()> {
        let name: String = result.getattr("seed_name")?.extract()?;
        let mut result: Bound<'_, PyAny> = result;
        if let Some(projector) = &self.projector {
            let duration: Bound<'_, PyAny> = call_with(
                &projector.bind(py).getattr("consume_resource_terminal")?,
                &[
                    ("resource_name", text(py, &name)),
                    ("resource_id", text(py, &format!("seed:{name}"))),
                ],
            )?;
            if !duration.is_none() {
                let milliseconds: Bound<'_, PyAny> =
                    py.import("builtins")?.getattr("int")?.call1((duration,))?;
                let changes: Bound<'_, PyDict> = PyDict::new(py);
                changes.set_item("duration_ms", milliseconds)?;
                result = py
                    .import("dataclasses")?
                    .getattr("replace")?
                    .call((result,), Some(&changes))?;
            }
        }
        let ordinal: usize = *self
            .ordinals
            .get(&name)
            .ok_or_else(|| PyKeyError::new_err(name.clone()))?;
        let style: CliStyle = CliStyle {
            use_color: self.use_color,
        };
        let row: SeedRow = SeedRow {
            name,
            ordinal,
            total: self.total,
            succeeded: status_value(&result)? == SUCCESS_STATUS,
            duration_ms: result.getattr("duration_ms")?.extract()?,
            error_message: result.getattr("error_message")?.extract()?,
            error_code: result.getattr("error_code")?.extract()?,
            error_help: result.getattr("error_help")?.extract()?,
        };
        let stream: &Bound<'_, PyAny> = self.stream.bind(py);
        stream.call_method1("write", (render_seed_row(&row, style),))?;
        stream.call_method0("flush")?;
        call_with(
            &self.event_writer.bind(py).getattr("write_build_result")?,
            &[
                ("result", result),
                ("plan", self.plan.bind(py).clone()),
                ("command", text(py, "seed")),
            ],
        )?;
        Ok(())
    }
}

/// Compile the selected seeds, reading their stored fingerprints when any are selected.
fn compile_seeds<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let stream: Bound<'py, PyAny> = invocation.getattr("progress_stream")?;
    let adapter: Bound<'py, PyAny> = invocation.getattr("adapter")?;
    let connection_config: Bound<'py, PyAny> = invocation.getattr("connection_config")?;
    let discovered: Bound<'py, PyAny> = invocation.getattr("discovered_inputs")?;
    let connection_progress: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::ConnectionProgressReporter)?,
        &[
            ("adapter_name", invocation.getattr("adapter_name")?),
            ("stream", stream.clone()),
            ("use_color", invocation.getattr("use_color")?),
        ],
    )?;
    stream.call_method1("write", ("\n",))?;
    stream.call_method0("flush")?;
    let resolver: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::ResolveExternalSqlReferenceResolver)?,
        &[
            ("project_dir", invocation.getattr("effective_project_dir")?),
            ("discovered_inputs", discovered.clone()),
        ],
    )?;
    let options: Bound<'py, PyAny> = call_with(
        &registry::class(py, RecordId::CompilePipelineOptions)?,
        &[
            ("selected_target", request.getattr("selected_target")?),
            ("select", request.getattr("select")?),
            ("exclude", request.getattr("exclude")?),
            ("connection_config", connection_config.clone()),
            ("cli_vars", request.getattr("cli_vars")?),
            ("external_sql_reference_resolver", resolver),
        ],
    )?;
    let context: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::CompileStaticCommandContext)?,
        &[
            ("discovered_inputs", discovered),
            ("adapter", adapter.clone()),
            ("options", options),
        ],
    )?;
    let project: Bound<'py, PyAny> = context.getattr("project")?;
    let scope: Bound<'py, PyAny> = context.getattr("scope")?;
    let selected_keys: Bound<'py, PyAny> = scope.getattr("selected_keys")?;
    let mut selected: Vec<Bound<'py, PyAny>> = Vec::new();
    for seed in project.getattr("seeds")?.try_iter()? {
        let seed: Bound<'py, PyAny> = seed?;
        if selected_keys.contains(seed.getattr("key")?)? {
            selected.push(seed);
        }
    }
    let fingerprints: Bound<'py, PyAny> = if selected.is_empty() {
        PyDict::new(py).into_any()
    } else {
        let relay: Bound<'py, SeedConnectionRelay> = connection_relay(&connection_progress)?;
        let hooks: Bound<'py, PyAny> = call_with(
            &host::entry(py, ExecutorHost::ConnectionHooks)?,
            &[
                (
                    "on_connection_start",
                    connection_progress.getattr("on_connection_start")?,
                ),
                (
                    "on_connection_complete",
                    relay.getattr("on_connection_complete")?,
                ),
                ("on_connection_error", relay.getattr("on_connection_error")?),
            ],
        )?;
        let connection: Bound<'py, PyAny> =
            connection_with_hooks(&adapter, &connection_config, &hooks)?;
        let read: PyResult<Bound<'py, PyAny>> = call_with(
            &registry::native(py, NativeAttr::ReadSelectedSeedFingerprints)?,
            &[
                ("adapter", adapter.clone()),
                ("connection", connection.clone()),
                ("seeds", PyTuple::new(py, &selected)?.into_any()),
            ],
        );
        let closed: PyResult<Bound<'py, PyAny>> = adapter.call_method1("close", (connection,));
        let read: Bound<'py, PyAny> = read?;
        closed?;
        read
    };
    let plan_output: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::BuildSeedCommandPlan)?,
        &[
            ("project", project),
            ("scope", scope),
            ("relations", context.getattr("relations")?),
            ("fingerprints", fingerprints),
        ],
    )?;
    call_with(
        &registry::native(py, NativeAttr::BuildStaticPipelineResult)?,
        &[("context", context), ("plan_output", plan_output)],
    )
}

fn seed_names(pipeline: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    pipeline
        .getattr("plan_output")?
        .getattr("seed_entries")?
        .try_iter()?
        .map(|entry| entry?.getattr("name")?.extract())
        .collect()
}

/// Write the ready header, the selected seeds and the execution header.
fn write_header(
    invocation: &Bound<'_, PyAny>,
    pipeline: &Bound<'_, PyAny>,
    concurrency: i64,
) -> PyResult<()> {
    let py: Python<'_> = invocation.py();
    let stream: Bound<'_, PyAny> = invocation.getattr("progress_stream")?;
    let use_color: Bound<'_, PyAny> = invocation.getattr("use_color")?;
    let style: CliStyle = CliStyle {
        use_color: use_color.is_truthy()?,
    };
    stream.call_method1("write", (render_seed_ready(&seed_names(pipeline)?, style),))?;
    let header: Bound<'_, PyDict> = PyDict::new(py);
    header.set_item("stream", &stream)?;
    header.set_item("command", EXECUTION_COMMAND)?;
    header.set_item("target", py.None())?;
    header.set_item("concurrency", concurrency)?;
    header.set_item("use_color", use_color)?;
    registry::native(py, NativeAttr::WriteExecutionHeader)?.call((), Some(&header))?;
    Ok(())
}

/// Load the planned seeds, writing one row per finished seed.
fn load_seeds<'py>(
    invocation: &Bound<'py, PyAny>,
    pipeline: &Bound<'py, PyAny>,
    concurrency: i64,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py: Python<'py> = invocation.py();
    let stream: Bound<'py, PyAny> = invocation.getattr("progress_stream")?;
    let use_color: Bound<'py, PyAny> = invocation.getattr("use_color")?;
    let plan: Bound<'py, PyAny> = pipeline.getattr("plan_output")?;
    let project: Bound<'py, PyAny> = pipeline.getattr("project")?;
    let names: Vec<String> = seed_names(pipeline)?;
    let ordinals: HashMap<String, usize> = names
        .iter()
        .enumerate()
        .map(|(index, name)| (name.clone(), index + 1))
        .collect();
    let event_writer: Bound<'py, PyAny> =
        registry::native(py, NativeAttr::ExecutionEventWriter)?.call0()?;
    let projector: Bound<'py, PyAny> =
        registry::native(py, NativeAttr::CurrentNativeProgressProjector)?.call0()?;
    let projector: Option<Py<PyAny>> = if projector.is_none() {
        None
    } else {
        let order: Bound<'py, PyDict> = PyDict::new(py);
        for (index, name) in names.iter().enumerate() {
            order.set_item(name, index + 1)?;
        }
        call_with(
            &projector.getattr("configure_resources")?,
            &[
                ("ordinals", order.into_any()),
                ("total", PyInt::new(py, names.len()).into_any()),
            ],
        )?;
        Some(projector.unbind())
    };
    let completion: Bound<'py, SeedCompletionRelay> = Bound::new(
        py,
        SeedCompletionRelay {
            stream: stream.clone().unbind(),
            use_color: use_color.is_truthy()?,
            ordinals,
            total: names.len(),
            event_writer: event_writer.clone().unbind(),
            plan: plan.clone().unbind(),
            projector,
        },
    )?;
    let connection_progress: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::ConnectionProgressReporter)?,
        &[
            ("adapter_name", invocation.getattr("adapter_name")?),
            ("stream", stream),
            (
                "blank_line_after_complete",
                PyBool::new(py, true).to_owned().into_any(),
            ),
            ("use_color", use_color),
        ],
    )?;
    let relay: Bound<'py, SeedConnectionRelay> = connection_relay(&connection_progress)?;
    let loaded: PyResult<Vec<Bound<'py, PyAny>>> = (|| {
        call_with(
            &host::entry(py, ExecutorHost::RunSeedPipeline)?,
            &[
                ("plan", plan),
                (
                    "connection_config",
                    invocation.getattr("connection_config")?,
                ),
                ("adapter", invocation.getattr("adapter")?),
                ("max_concurrency", PyInt::new(py, concurrency).into_any()),
                ("run_id", project.getattr("run_id")?),
                (
                    "query_change_tracking",
                    project
                        .getattr("settings")?
                        .getattr("query_change_tracking")?,
                ),
                ("on_seed_complete", completion.getattr("on_seed_complete")?),
                (
                    "on_connection_start",
                    connection_progress.getattr("on_connection_start")?,
                ),
                (
                    "on_connection_complete",
                    relay.getattr("on_connection_complete")?,
                ),
                ("on_connection_error", relay.getattr("on_connection_error")?),
            ],
        )?
        .try_iter()?
        .collect()
    })();
    let closed: PyResult<Bound<'py, PyAny>> = event_writer.call_method0("close");
    let results: Vec<Bound<'py, PyAny>> = loaded?;
    closed?;
    Ok(results)
}

/// Run one `sqb seed` request.
#[pyfunction]
#[pyo3(signature = (*, request))]
fn run_seed_command(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let invocation: Bound<'_, PyAny> =
        resolve_command_invocation(request, &registry::class(py, RecordId::SeedInvocation)?)?;
    let pipeline: Bound<'_, PyAny> = compile_seeds(request, &invocation)?;
    let requested: Bound<'_, PyAny> = request.getattr("concurrency")?;
    let concurrency: i64 = if requested.is_none() {
        pipeline
            .getattr("project")?
            .getattr("settings")?
            .getattr("concurrency")?
            .extract::<i64>()?
    } else {
        requested.extract::<i64>()?
    }
    .max(1);
    write_header(&invocation, &pipeline, concurrency)?;
    let started: Instant = Instant::now();
    let results: Vec<Bound<'_, PyAny>> = load_seeds(&invocation, &pipeline, concurrency)?;
    let elapsed: f64 = started.elapsed().as_secs_f64();
    let mut passed: usize = 0;
    let mut failed: usize = 0;
    for result in &results {
        match status_value(result)?.as_str() {
            SUCCESS_STATUS => passed += 1,
            FAILED_STATUS => failed += 1,
            _ => {}
        }
    }
    let stream: Bound<'_, PyAny> = invocation.getattr("progress_stream")?;
    let style: CliStyle = CliStyle {
        use_color: invocation.getattr("use_color")?.is_truthy()?,
    };
    stream.call_method1(
        "write",
        (render_seed_completion(
            (passed, failed, results.len()),
            elapsed,
            style,
        ),),
    )?;
    stream.call_method0("flush")?;
    let payload: Bound<'_, PyAny> = call_with(
        &registry::native(py, NativeAttr::FormatSeedExecutionJson)?,
        &[
            ("results", PyTuple::new(py, &results)?.into_any()),
            ("plan", pipeline.getattr("plan_output")?),
        ],
    )?;
    call_with(
        &registry::native(py, NativeAttr::WriteExecutionJsonOutput)?,
        &[
            ("payload", payload),
            ("json_output", request.getattr("json_output")?),
            ("json_output_path", request.getattr("json_output_path")?),
        ],
    )?;
    Ok(seed_exit_code(failed))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_seed_command, module)?)?;
    Ok(())
}
