//! `sqb audit`: compile the selected audits, run them with nested progress, and report.

use std::collections::BTreeSet;

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyInt, PyList, PyListMethods, PyString, PyTuple};
use pyo3::{pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_core::audit_command::main::audit_exit_code::audit_exit_code;
use sqlbuild_core::audit_command::main::render_audit_header::render_audit_header;
use sqlbuild_core::audit_command::main::render_audit_summary::render_audit_summary;
use sqlbuild_core::audit_command::models::AuditCounts;
use sqlbuild_core::cli_text::models::CliStyle;

use crate::bindings::_helpers::command_runtime::invocation::resolve_reported_command_invocation;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, within};

const NATIVE_MODULE: &str = "sqlbuild._native";
const COMMAND_MODELS: &str = "sqlbuild.cli.commands.models";
const EXTERNAL_REFS_MODULE: &str = "sqlbuild.cli.commands._helpers.planning.external_refs";
const STATIC_COMMAND_MODULE: &str = "sqlbuild._native";
const PIPELINE_MODELS: &str = "sqlbuild.compiler.pipeline.models";
const AUDIT_PLAN_MODULE: &str = "sqlbuild.compiler.planner.main.commands._audit";
const COST_CONTEXT_MODULE: &str = "sqlbuild.cost.classes.cost_context";
const EXECUTOR_RUN_MODULE: &str = "sqlbuild.executor.pipeline.main.run";
const PROJECTION_MODULE: &str = "sqlbuild.executor.auditing.main._current_audit_result_projection";
const EXECUTION_COMMAND: &str = "sqb audit";
const PASS_OUTCOME: &str = "pass";
const WARN_OUTCOME: &str = "warn";
const ERROR_OUTCOME: &str = "error";
const INSUFFICIENT_OUTCOME: &str = "insufficient";
const PROJECTION_FAILURE: &str = "audit_result_projection_failure";

fn text<'py>(py: Python<'py>, value: &str) -> Bound<'py, PyAny> {
    PyString::new(py, value).into_any()
}

/// Forward audit results to the event writer and connection timing to its reporter.
#[pyclass(module = "sqlbuild._native", frozen)]
struct AuditCallbackRelay {
    event_writer: Py<PyAny>,
    plan: Py<PyAny>,
    connection: Py<PyAny>,
}

#[pymethods]
impl AuditCallbackRelay {
    fn on_result(&self, py: Python<'_>, result: Bound<'_, PyAny>) -> PyResult<()> {
        call_with(
            &self.event_writer.bind(py).getattr("write_build_result")?,
            &[
                ("result", result),
                ("plan", self.plan.bind(py).clone()),
                ("command", text(py, "audit")),
            ],
        )?;
        Ok(())
    }

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

impl AuditCallbackRelay {
    fn forward(
        &self,
        py: Python<'_>,
        method: &str,
        (connection_count, elapsed_seconds): (i64, f64),
    ) -> PyResult<()> {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("connection_count", connection_count)?;
        options.set_item("elapsed_seconds", elapsed_seconds)?;
        self.connection
            .bind(py)
            .call_method(method, (), Some(&options))?;
        Ok(())
    }
}

/// Compile the audit plan for the selected scope.
fn compile_audits<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let discovered: Bound<'py, PyAny> = invocation.getattr("discovered_inputs")?;
    let adapter: Bound<'py, PyAny> = invocation.getattr("adapter")?;
    let resolver: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            EXTERNAL_REFS_MODULE,
            "resolve_external_sql_reference_resolver",
        )?,
        &[
            ("project_dir", invocation.getattr("effective_project_dir")?),
            ("discovered_inputs", discovered.clone()),
        ],
    )?;
    let options: Bound<'py, PyAny> = call_with(
        &imported(py, PIPELINE_MODELS, "CompilePipelineOptions")?,
        &[
            ("selected_target", request.getattr("selected_target")?),
            ("no_sql_validation", request.getattr("no_sql_validation")?),
            ("defer_to", request.getattr("defer_to")?),
            ("select", request.getattr("select")?),
            ("exclude", request.getattr("exclude")?),
            (
                "connection_config",
                invocation.getattr("connection_config")?,
            ),
            ("cli_vars", request.getattr("cli_vars")?),
            ("external_sql_reference_resolver", resolver),
        ],
    )?;
    let context: Bound<'py, PyAny> = call_with(
        &imported(py, STATIC_COMMAND_MODULE, "compile_static_command_context")?,
        &[
            ("discovered_inputs", discovered),
            ("adapter", adapter.clone()),
            ("options", options),
            (
                "on_progress",
                invocation
                    .getattr("planning_progress")?
                    .getattr("on_progress")?,
            ),
        ],
    )?;
    let plan_output: Bound<'py, PyAny> = call_with(
        &imported(py, AUDIT_PLAN_MODULE, "build_audit_command_plan")?,
        &[
            ("project", context.getattr("project")?),
            ("adapter", adapter),
            ("scope", context.getattr("scope")?),
            ("relations", context.getattr("relations")?),
        ],
    )?;
    call_with(
        &imported(py, NATIVE_MODULE, "build_static_pipeline_result")?,
        &[("context", context), ("plan_output", plan_output)],
    )
}

/// The audits run with their progress and connection reporters.
struct AuditRun<'py> {
    progress: Bound<'py, PyAny>,
    connection: Bound<'py, PyAny>,
    concurrency: i64,
    worker_count: i64,
}

/// Create the nested progress and connection reporters before the execution header.
fn prepare_run<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Bound<'py, PyAny>,
    pipeline: &Bound<'py, PyAny>,
) -> PyResult<AuditRun<'py>> {
    let py: Python<'py> = request.py();
    let entries: Bound<'py, PyAny> = pipeline.getattr("plan_output")?.getattr("audit_entries")?;
    let requested: Bound<'py, PyAny> = request.getattr("concurrency")?;
    let concurrency: i64 = if requested.is_none() {
        pipeline
            .getattr("project")?
            .getattr("settings")?
            .getattr("concurrency")?
            .extract::<i64>()?
    } else {
        requested.extract::<i64>()?
    };
    let audit_count: usize = entries.len()?;
    let worker_count: i64 = concurrency.min(i64::try_from(audit_count).unwrap_or(i64::MAX));
    let stream: Bound<'py, PyAny> = invocation.getattr("progress_stream")?;
    let use_color: Bound<'py, PyAny> = invocation.getattr("use_color")?;
    let progress: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "AuditProgressReporter")?,
        &[
            ("entries", entries.clone()),
            ("worker_limit", PyInt::new(py, worker_count).into_any()),
            ("stream", stream.clone()),
            ("use_color", use_color.clone()),
        ],
    )?;
    let projector: Bound<'py, PyAny> =
        imported(py, NATIVE_MODULE, "current_native_progress_projector")?.call0()?;
    if !projector.is_none() {
        for entry in entries.try_iter()? {
            call_with(
                &projector.getattr("expect_resource_enrichment")?,
                &[("resource_name", entry?.getattr("name")?)],
            )?;
        }
    }
    let connection: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "ConnectionProgressReporter")?,
        &[
            ("adapter_name", invocation.getattr("adapter_name")?),
            ("stream", stream),
            ("use_color", use_color),
        ],
    )?;
    Ok(AuditRun {
        progress,
        connection,
        concurrency,
        worker_count,
    })
}

/// Write the execution header, then the selected audits header.
fn write_headers(
    invocation: &Bound<'_, PyAny>,
    pipeline: &Bound<'_, PyAny>,
    concurrency: i64,
) -> PyResult<()> {
    let py: Python<'_> = invocation.py();
    let stream: Bound<'_, PyAny> = invocation.getattr("progress_stream")?;
    let use_color: Bound<'_, PyAny> = invocation.getattr("use_color")?;
    stream.call_method1("write", ("\n",))?;
    let header: Bound<'_, PyDict> = PyDict::new(py);
    header.set_item("stream", &stream)?;
    header.set_item("command", EXECUTION_COMMAND)?;
    header.set_item("target", py.None())?;
    header.set_item("concurrency", concurrency)?;
    header.set_item("use_color", &use_color)?;
    imported(py, NATIVE_MODULE, "write_execution_header")?.call((), Some(&header))?;
    let entries: Bound<'_, PyAny> = pipeline.getattr("plan_output")?.getattr("audit_entries")?;
    let mut models: BTreeSet<String> = BTreeSet::new();
    for entry in entries.try_iter()? {
        let target: Bound<'_, PyAny> = entry?.getattr("attached_target_name")?;
        if target.is_truthy()? {
            models.insert(target.extract()?);
        }
    }
    let style: CliStyle = CliStyle {
        use_color: use_color.is_truthy()?,
    };
    stream.call_method1(
        "write",
        (render_audit_header((entries.len()?, models.len()), style),),
    )?;
    stream.call_method0("flush")?;
    Ok(())
}

/// Run the audits inside the run's cost scope; returns their results.
fn execute<'py>(
    invocation: &Bound<'py, PyAny>,
    pipeline: &Bound<'py, PyAny>,
    run: &AuditRun<'py>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py: Python<'py> = invocation.py();
    let plan: Bound<'py, PyAny> = pipeline.getattr("plan_output")?;
    let project: Bound<'py, PyAny> = pipeline.getattr("project")?;
    let event_writer: Bound<'py, PyAny> =
        imported(py, NATIVE_MODULE, "ExecutionEventWriter")?.call0()?;
    let relay: Bound<'py, AuditCallbackRelay> = Bound::new(
        py,
        AuditCallbackRelay {
            event_writer: event_writer.clone().unbind(),
            plan: plan.clone().unbind(),
            connection: run.connection.clone().unbind(),
        },
    )?;
    let executed: PyResult<Vec<Bound<'py, PyAny>>> = (|| {
        run.progress
            .call_method1("set_result_callback", (relay.getattr("on_result")?,))?;
        let projector: Bound<'py, PyAny> =
            imported(py, NATIVE_MODULE, "current_native_progress_projector")?.call0()?;
        if !projector.is_none() {
            let ordinals: Bound<'py, PyDict> = PyDict::new(py);
            let mut total: usize = 0;
            for entry in plan.getattr("audit_entries")?.try_iter()? {
                total += 1;
                ordinals.set_item(entry?.getattr("name")?, total)?;
            }
            call_with(
                &projector.getattr("configure_resources")?,
                &[
                    ("ordinals", ordinals.into_any()),
                    ("total", PyInt::new(py, total).into_any()),
                ],
            )?;
        }
        let run_id: Bound<'py, PyAny> = project.getattr("run_id")?;
        let ledger_path: Bound<'py, PyAny> = invocation
            .getattr("effective_project_dir")?
            .call_method1("__truediv__", ("target",))?
            .call_method1("__truediv__", ("executions",))?
            .call_method1("__truediv__", (&run_id,))?
            .call_method1("__truediv__", ("statements.jsonl",))?;
        let scope: Bound<'py, PyAny> = call_with(
            &imported(py, COST_CONTEXT_MODULE, "CostContext")?.getattr("scope")?,
            &[
                ("run_id", run_id.clone()),
                ("resource_type", text(py, "run")),
                ("resource_name", text(py, "audit")),
                ("ledger_path", ledger_path),
                ("phase", text(py, "audit")),
            ],
        )?;
        within(&scope, |_| {
            let callbacks: Bound<'py, PyAny> = call_with(
                &imported(py, EXECUTOR_RUN_MODULE, "AuditPipelineCallbacks")?,
                &[
                    (
                        "on_connection_start",
                        run.connection.getattr("on_connection_start")?,
                    ),
                    (
                        "on_connection_complete",
                        relay.getattr("on_connection_complete")?,
                    ),
                    ("on_connection_error", relay.getattr("on_connection_error")?),
                    ("on_audit_start", run.progress.getattr("on_item_start")?),
                    (
                        "on_audit_physical_complete",
                        run.progress.getattr("on_item_physical_complete")?,
                    ),
                    (
                        "on_audit_complete",
                        run.progress.getattr("on_item_complete")?,
                    ),
                    ("on_audit_error", run.progress.getattr("on_item_error")?),
                ],
            )?;
            call_with(
                &imported(py, EXECUTOR_RUN_MODULE, "run_audit_pipeline_with_callbacks")?,
                &[
                    ("plan", plan.clone()),
                    (
                        "connection_config",
                        invocation.getattr("connection_config")?,
                    ),
                    ("adapter", invocation.getattr("adapter")?),
                    (
                        "max_concurrency",
                        PyInt::new(py, run.concurrency).into_any(),
                    ),
                    ("callbacks", callbacks),
                    ("run_id", run_id.clone()),
                    (
                        "storage_database",
                        project.getattr("effective_target_database")?,
                    ),
                    (
                        "storage_schema",
                        project.getattr("effective_target_schema")?,
                    ),
                ],
            )?
            .try_iter()?
            .collect()
        })
    })();
    let progress_closed: PyResult<Bound<'py, PyAny>> = run.progress.call_method0("close");
    let writer_closed: PyResult<Bound<'py, PyAny>> = event_writer.call_method0("close");
    let results: Vec<Bound<'py, PyAny>> = executed?;
    progress_closed?;
    writer_closed?;
    Ok(results)
}

/// The audit JSON document, with the result projection counts when audits were projected.
fn audit_payload<'py>(
    results: &Bound<'py, PyAny>,
    (concurrency, worker_count): (i64, i64),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = results.py();
    let payload: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "format_audit_execution_json")?,
        &[
            ("results", results.clone()),
            (
                "configured_concurrency",
                PyInt::new(py, concurrency).into_any(),
            ),
            ("worker_count", PyInt::new(py, worker_count).into_any()),
        ],
    )?;
    let projection: Bound<'py, PyAny> =
        imported(py, PROJECTION_MODULE, "current_audit_result_projection")?.call0()?;
    if projection.is_none() {
        return Ok(payload);
    }
    let json: Bound<'py, PyAny> = py.import("json")?.into_any();
    let document: Bound<'py, PyAny> = json.call_method1("loads", (payload,))?;
    let counts: Bound<'py, PyDict> = PyDict::new(py);
    for field in ["attempted_count", "written_count", "failed_count"] {
        counts.set_item(field, projection.getattr(field)?)?;
    }
    document.set_item("audit_result_projection", &counts)?;
    if projection.getattr("degraded")?.is_truthy()? {
        document.set_item("projection_degraded", true)?;
        let reason: Bound<'py, PyDict> = PyDict::new(py);
        reason.set_item("reason", PROJECTION_FAILURE)?;
        for field in ["attempted_count", "written_count", "failed_count"] {
            reason.set_item(field, projection.getattr(field)?)?;
        }
        let reasons: Bound<'py, PyList> = PyList::empty(py);
        reasons.append(reason)?;
        document.set_item("projection_degradation_reasons", reasons)?;
    }
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item("indent", 2)?;
    let dumped: String = json
        .call_method("dumps", (document,), Some(&options))?
        .extract()?;
    Ok(PyString::new(py, &format!("{dumped}\n")).into_any())
}

/// Write the summary footer and JSON output; returns the exit code.
fn complete(
    request: &Bound<'_, PyAny>,
    invocation: &Bound<'_, PyAny>,
    results: &[Bound<'_, PyAny>],
    run: &AuditRun<'_>,
) -> PyResult<i32> {
    let py: Python<'_> = request.py();
    let mut counts: AuditCounts = AuditCounts {
        total: results.len(),
        ..AuditCounts::default()
    };
    for result in results {
        match result
            .getattr("outcome")?
            .getattr("value")?
            .extract::<String>()?
            .as_str()
        {
            PASS_OUTCOME => counts.passed += 1,
            WARN_OUTCOME => counts.warned += 1,
            ERROR_OUTCOME => counts.failed += 1,
            INSUFFICIENT_OUTCOME => counts.insufficient += 1,
            _ => {}
        }
    }
    let stream: Bound<'_, PyAny> = invocation.getattr("progress_stream")?;
    let style: CliStyle = CliStyle {
        use_color: invocation.getattr("use_color")?.is_truthy()?,
    };
    stream.call_method1("write", (render_audit_summary(counts, style),))?;
    stream.call_method0("flush")?;
    let payload: Bound<'_, PyAny> = audit_payload(
        &PyTuple::new(py, results)?.into_any(),
        (run.concurrency, run.worker_count),
    )?;
    call_with(
        &imported(py, NATIVE_MODULE, "write_execution_json_output")?,
        &[
            ("payload", payload),
            ("json_output", request.getattr("json_output")?),
            ("json_output_path", request.getattr("json_output_path")?),
        ],
    )?;
    Ok(audit_exit_code(counts.failed))
}

/// Run one `sqb audit` request.
#[pyfunction]
#[pyo3(signature = (*, request))]
fn run_audit_command(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let invocation: Bound<'_, PyAny> = resolve_reported_command_invocation(
        request,
        &imported(py, COMMAND_MODELS, "AuditInvocation")?,
        true,
    )?;
    let pipeline: Bound<'_, PyAny> = compile_audits(request, &invocation)?;
    let run: AuditRun<'_> = prepare_run(request, &invocation, &pipeline)?;
    write_headers(&invocation, &pipeline, run.concurrency)?;
    let results: Vec<Bound<'_, PyAny>> = execute(&invocation, &pipeline, &run)?;
    complete(request, &invocation, &results, &run)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_audit_command, module)?)?;
    Ok(())
}
