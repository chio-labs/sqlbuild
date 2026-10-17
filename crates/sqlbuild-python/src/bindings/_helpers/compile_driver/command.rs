//! The `sqb compile` command: analysis, output phases, reuse recording and printed output.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyMapping, PyString, PyTuple};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use std::rc::Rc;

use crate::bindings::_helpers::build_progress::transient_status::status_reporter;
use crate::bindings::_helpers::compile_command::models::CompileReuseAttempt;
use crate::bindings::_helpers::compile_command::report::{
    format_compile_json, format_compile_text, json_semantic_notice,
};
use crate::bindings::_helpers::compile_command::reuse_recording::write_reusable_compile;
use crate::bindings::_helpers::compile_command::reuse_recording::{
    CompileArtifactWrites, RecordedCompileOutput, compile_reuse_timings, new_artifact_recorder,
};
use crate::bindings::_helpers::compile_driver::analysis::analyze;
use crate::bindings::_helpers::compile_driver::compile_timings::{
    CompileTimingsHandle, collect_compile_timings, timing_milliseconds,
};
use crate::bindings::_helpers::compile_driver::input_reads::record_compile_input_reads;
use crate::bindings::_helpers::compile_driver::phases::{
    elapsed_ms, manifest_payload, monotonic, resolved_dag_path, sql_test_planning_diagnostics,
    target_dir, write_artifacts, write_dag_artifact,
};
use crate::bindings::_helpers::compile_driver::python_calls::{
    Status, call_with, imported, keywords, within,
};
use crate::bindings::_helpers::presentation_text::terminal::stdout_supports_color;
use crate::bindings::_helpers::records::construct::{enum_member, new_record_with};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::replaced;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::rules::results::format_skipped_type_proof_rules;

const BYPASS_OUTCOME: &str = "bypass";

/// What one full compile reports for reuse recording.
struct CommandOutcome<'py> {
    exit_code: i64,
    compile_cache_enabled: bool,
    artifacts_written: bool,
    dag_artifact_path: Bound<'py, PyAny>,
}

/// The per-invocation recorders a compile runs inside.
struct Recorders<'py> {
    detailed_timings: CompileTimingsHandle,
    input_reads: Bound<'py, PyAny>,
    artifact_writes: Py<CompileArtifactWrites>,
    prepared_artifacts: Bound<'py, PyAny>,
}

/// Run one full compile, recording it for reuse; returns the exit code.
#[pyfunction]
#[pyo3(signature = (request, reuse_attempt=None))]
pub(crate) fn run_compile_command<'py>(
    py: Python<'py>,
    request: Bound<'py, PyAny>,
    reuse_attempt: Option<Bound<'py, PyAny>>,
) -> PyResult<i64> {
    let total_start: f64 = match &reuse_attempt {
        Some(attempt) => native_field(attempt, "started")?.extract()?,
        None => monotonic(py)?,
    };
    let path_class: Bound<'py, PyAny> = imported(py, "pathlib", "Path")?;
    let effective_request: Bound<'py, PyAny> = if native_field(&request, "project_dir")?.is_none() {
        replaced(
            &request.clone(),
            &[("project_dir", path_class.call_method0("cwd")?)],
        )?
    } else {
        request.clone()
    };
    let attempt: Bound<'py, PyAny> = match reuse_attempt {
        Some(attempt) => attempt,
        None => bypass_attempt(py, &effective_request, total_start)?,
    };
    let output: Bound<'py, PyAny> = Bound::new(py, RecordedCompileOutput::new())?.into_any();
    let status: Status<'py> = Status(compile_status(&request)?);
    let gc: Bound<'py, PyModule> = py.import("gc")?;
    let was_enabled: bool = gc.call_method0("isenabled")?.is_truthy()?;
    gc.call_method0("disable")?;
    let exit_code: PyResult<i64> = recorded_compile(
        (&effective_request, &attempt),
        (&output, &status),
        total_start,
    );
    if was_enabled {
        gc.call_method0("enable")?;
    }
    exit_code
}

/// `CompileReuseAttempt` of a compile that did not consult the reuse record.
fn bypass_attempt<'py>(
    py: Python<'py>,
    request: &Bound<'py, PyAny>,
    started: f64,
) -> PyResult<Bound<'py, PyAny>> {
    let path_class: Bound<'py, PyAny> = imported(py, "pathlib", "Path")?;
    let project_dir: Bound<'py, PyAny> = native_field(request, "project_dir")?;
    let project_dir: Bound<'py, PyAny> = if project_dir.is_truthy()? {
        project_dir
    } else {
        path_class.call_method0("cwd")?
    };
    call_with(
        py.get_type::<CompileReuseAttempt>().as_any(),
        &[
            ("outcome", BYPASS_OUTCOME.into_pyobject(py)?.into_any()),
            ("project_dir", path_class.call1((project_dir,))?),
            ("started", started.into_pyobject(py)?.into_any()),
        ],
    )
}

/// The interactive status line, shown only on a terminal without `--json`.
fn compile_status<'py>(request: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let none: Bound<'py, PyAny> = py.None().into_bound(py);
    if native_field(request, "json_output")?.is_truthy()? {
        return Ok(none);
    }
    let stdout: Bound<'py, PyAny> = py.import("sys")?.getattr("stdout")?;
    if !stdout.hasattr("isatty")? || !stdout.call_method0("isatty")?.is_truthy()? {
        return Ok(none);
    }
    let use_color: bool = !native_field(request, "no_color")?.is_truthy()?;
    status_reporter(&stdout, use_color)
}

/// Close the status line when one is shown.
fn close_status(status: &Status<'_>) -> PyResult<()> {
    if !status.0.is_none() {
        status.0.call_method0("close")?;
    }
    Ok(())
}

/// Compile inside the recorders, then store the reusable compile and print its output.
fn recorded_compile<'py>(
    (request, attempt): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (output, status): (&Bound<'py, PyAny>, &Status<'py>),
    total_start: f64,
) -> PyResult<i64> {
    let py: Python<'py> = request.py();
    let skip_write: bool = native_field(request, "profile_flags")?
        .getattr("skip_write")?
        .is_truthy()?;
    let compiled: PyResult<(CommandOutcome<'py>, Bound<'py, PyAny>, Bound<'py, PyAny>)> =
        collect_compile_timings(|detailed_timings| {
            within(
                &Bound::new(py, record_compile_input_reads())?.into_any(),
                |input_reads| {
                    let artifact_writes: Py<CompileArtifactWrites> = new_artifact_recorder(py)?;
                    let manager: Bound<'py, PyAny> = call_with(
                        &registry::native(py, NativeAttr::PreparedCompileArtifacts)?,
                        &[
                            (
                                "enabled",
                                PyBool::new(py, !skip_write).to_owned().into_any(),
                            ),
                            (
                                "artifact_writes",
                                artifact_writes.bind(py).clone().into_any(),
                            ),
                        ],
                    )?;
                    within(&manager, |prepared_artifacts| {
                        let recorders: Recorders<'py> = Recorders {
                            detailed_timings: Rc::clone(detailed_timings),
                            input_reads: input_reads.clone(),
                            artifact_writes: artifact_writes.clone_ref(py),
                            prepared_artifacts: prepared_artifacts.clone(),
                        };
                        let reuse_timings: Bound<'py, PyAny> =
                            compile_reuse_timings(attempt)?.into_any();
                        let outcome: CommandOutcome<'py> = compiled_with_status(
                            (request, &recorders),
                            (status, output),
                            (total_start, &reuse_timings),
                        )?;
                        Ok((
                            outcome,
                            recorders.input_reads,
                            recorders.artifact_writes.into_bound(py).into_any(),
                        ))
                    })
                },
            )
        });
    close_status(status)?;
    let (outcome, input_reads, artifact_writes) = compiled?;
    let stored: PyResult<()> = write_reusable_compile(
        py,
        Some(keywords(
            py,
            &[
                ("attempt", attempt.clone()),
                ("output", output.clone()),
                ("exit_code", outcome.exit_code.into_pyobject(py)?.into_any()),
                ("input_reads", input_reads),
                ("artifact_writes", artifact_writes),
                (
                    "compile_cache_enabled",
                    PyBool::new(py, outcome.compile_cache_enabled)
                        .to_owned()
                        .into_any(),
                ),
                (
                    "artifacts_written",
                    PyBool::new(py, outcome.artifacts_written)
                        .to_owned()
                        .into_any(),
                ),
                ("dag_artifact_path", outcome.dag_artifact_path),
                ("json_output", native_field(request, "json_output")?),
            ],
        )?),
    );
    let printed: PyResult<Bound<'py, PyAny>> = output.call_method0("print_stdout");
    printed?;
    stored?;
    Ok(outcome.exit_code)
}

/// `_run_compile_with_status`: analyze, run the output phases and record the command output.
fn compiled_with_status<'py>(
    (request, recorders): (&Bound<'py, PyAny>, &Recorders<'py>),
    (status, output): (&Status<'py>, &Bound<'py, PyAny>),
    (total_start, reuse_timings): (f64, &Bound<'py, PyAny>),
) -> PyResult<CommandOutcome<'py>> {
    let py: Python<'py> = request.py();
    let project_dir: Bound<'py, PyAny> = native_field(request, "project_dir")?;
    let project_dir: Bound<'py, PyAny> = if project_dir.is_none() {
        imported(py, "pathlib", "Path")?.call_method0("cwd")?
    } else {
        project_dir
    };
    let prepared_artifacts: &Bound<'py, PyAny> = &recorders.prepared_artifacts;
    call_with(
        &native_field(prepared_artifacts, "remove_abandoned_staging")?,
        &[("target_dir", target_dir(&project_dir)?)],
    )?;
    let analysis: Bound<'py, PyAny> = analyze(
        py,
        &analysis_options(request, &project_dir, recorders, status)?,
    )?;
    let rules_failed: bool = rules_failed(&analysis)?;
    let skip_write: bool = native_field(request, "profile_flags")?
        .getattr("skip_write")?
        .is_truthy()?;
    let manifest_requested: bool = native_field(request, "manifest")?.is_truthy()?;
    let manifest: Bound<'py, PyAny> =
        manifest_payload(manifest_requested && !rules_failed, &analysis, status)?;
    let dag_path: Bound<'py, PyAny> = if rules_failed {
        py.None().into_bound(py)
    } else {
        native_field(request, "dag_path")?
    };
    let recorder: Option<&Py<CompileArtifactWrites>> = Some(&recorders.artifact_writes);
    write_dag_artifact((&dag_path, &project_dir), (&analysis, recorder), status)?;
    let (written, write_ms): (Bound<'py, PyAny>, i64) = write_artifacts(
        (skip_write || rules_failed, &project_dir),
        (&analysis, &manifest),
        (prepared_artifacts, recorder),
        status,
    )?;
    let timings: Bound<'py, PyDict> = timings_ms(
        (&analysis, write_ms),
        (&recorders.detailed_timings, reuse_timings),
        total_start,
    )?;
    let withheld: Bound<'py, PyAny> = if rules_failed && !skip_write {
        sql_test_planning_diagnostics(&project_dir, &analysis, (prepared_artifacts, recorder))?
    } else {
        PyTuple::empty(py).into_any()
    };
    let diagnostics: Bound<'py, PyTuple> = PyTuple::new(
        py,
        native_field(&analysis, "diagnostics")?
            .try_iter()?
            .chain(native_field(&written, "diagnostics")?.try_iter()?)
            .chain(withheld.try_iter()?)
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    let mut exit_code: i64 = 0;
    for diagnostic in diagnostics.as_any().try_iter()? {
        if native_field(&diagnostic?, "is_error")?.is_truthy()? {
            exit_code = 1;
            break;
        }
    }
    close_status(status)?;
    if let Some(skipped_note) = format_skipped_type_proof_rules(
        native_field(&analysis, "skipped_type_proof_rules")?.extract()?,
    ) {
        output.call_method1("print_stderr_line", (format!("note: {skipped_note}"),))?;
    }
    let dag_artifact_path: Bound<'py, PyAny> =
        if rules_failed || native_field(request, "dag_path")?.is_none() {
            py.None().into_bound(py)
        } else {
            resolved_dag_path(&project_dir, &native_field(request, "dag_path")?)?
        };
    let outcome: CommandOutcome<'py> = CommandOutcome {
        exit_code,
        compile_cache_enabled: !native_field(&analysis, "graph")?
            .getattr("project")?
            .getattr("compile_cache_dir")?
            .is_none(),
        artifacts_written: !(rules_failed || skip_write),
        dag_artifact_path,
    };
    record_output(
        (request, &analysis),
        (&written, &diagnostics, &timings),
        output,
    )?;
    Ok(outcome)
}

/// The keyword options of the analysis phase.
fn analysis_options<'py>(
    request: &Bound<'py, PyAny>,
    project_dir: &Bound<'py, PyAny>,
    recorders: &Recorders<'py>,
    status: &Status<'py>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = request.py();
    let selection: Bound<'py, PyAny> = new_record_with(
        py,
        RecordId::CompileAnalysisSelection,
        &[
            ("select", native_field(request, "select")?),
            ("exclude", native_field(request, "exclude")?),
            ("no_cache", native_field(request, "no_cache")?),
        ],
    )?;
    keywords(
        py,
        &[
            ("project_dir", project_dir.clone()),
            (
                "no_sql_validation",
                native_field(request, "no_sql_validation")?,
            ),
            ("selected_target", native_field(request, "selected_target")?),
            ("lineage_mode", native_field(request, "lineage_mode")?),
            ("cli_vars", native_field(request, "cli_vars")?),
            ("profile_flags", native_field(request, "profile_flags")?),
            ("analysis_selection", selection),
            ("status", status.0.clone()),
            ("prepared_artifacts", recorders.prepared_artifacts.clone()),
        ],
    )
}

/// Whether a rule finding failed the compile.
fn rules_failed(analysis: &Bound<'_, PyAny>) -> PyResult<bool> {
    let py: Python<'_> = analysis.py();
    let rule_phase: Bound<'_, PyAny> = enum_member(py, RecordId::DiagnosticPhase, "RULE")?;
    for diagnostic in native_field(analysis, "diagnostics")?.try_iter()? {
        let diagnostic: Bound<'_, PyAny> = diagnostic?;
        if native_field(&diagnostic, "is_error")?.is_truthy()?
            && native_field(&diagnostic, "phase")?.is(&rule_phase)
        {
            return Ok(true);
        }
    }
    Ok(false)
}

/// The compile's phase timings, in the order `--json` reports them.
fn timings_ms<'py>(
    (analysis, write_ms): (&Bound<'py, PyAny>, i64),
    (detailed_timings, reuse_timings): (&CompileTimingsHandle, &Bound<'py, PyAny>),
    total_start: f64,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = analysis.py();
    let timings: Bound<'py, PyDict> = PyDict::new(py);
    for (key, attribute) in [
        ("discover_ms", "discover_ms"),
        ("graph_ms", "graph_ms"),
        ("lineage_ms", "lineage_ms"),
        ("contracts_ms", "contract_ms"),
        ("contracts_cpu_ms", "contract_cpu_ms"),
        ("built_in_rules_ms", "built_in_rules_ms"),
        ("custom_rules_ms", "custom_rules_ms"),
        ("custom_rules_cpu_ms", "custom_rules_cpu_ms"),
        ("early_lint_wait_ms", "early_lint_wait_ms"),
        ("rule_cache_hits", "rule_cache_hits"),
        ("rule_cache_misses", "rule_cache_misses"),
    ] {
        timings.set_item(key, native_field(analysis, attribute)?)?;
    }
    timings.set_item("write_ms", write_ms)?;
    for (key, value) in timing_milliseconds(detailed_timings) {
        timings.set_item(key, value)?;
    }
    timings.update(reuse_timings.downcast::<PyMapping>()?)?;
    timings.set_item("total_ms", elapsed_ms(py, total_start)?)?;
    Ok(timings)
}

/// Record the command's text or JSON output, with the semantic coverage notice for JSON.
fn record_output<'py>(
    (request, analysis): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (written, diagnostics, timings): (
        &Bound<'py, PyAny>,
        &Bound<'py, PyTuple>,
        &Bound<'py, PyDict>,
    ),
    output: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let py: Python<'py> = request.py();
    let graph: Bound<'py, PyAny> = native_field(analysis, "graph")?;
    let selected_keys: Bound<'py, PyAny> = native_field(analysis, "selected_keys")?;
    let validation_enabled: Bound<'py, PyAny> = PyBool::new(
        py,
        !native_field(request, "no_sql_validation")?.is_truthy()?,
    )
    .to_owned()
    .into_any();
    let shared: [(&str, Bound<'py, PyAny>); 7] = [
        ("graph", graph.clone()),
        ("written", written.clone()),
        ("manifest", native_field(request, "manifest")?),
        ("lineage", native_field(analysis, "lineage")?),
        ("lineage_mode", native_field(request, "lineage_mode")?),
        ("diagnostics", diagnostics.clone().into_any()),
        ("selected_keys", selected_keys.clone()),
    ];
    let mut arguments: Vec<(&str, Bound<'py, PyAny>)> = shared.to_vec();
    let rendered: Bound<'py, PyString> = if native_field(request, "json_output")?.is_truthy()? {
        let notice: Option<Bound<'py, PyString>> =
            json_semantic_notice(&graph, &selected_keys, validation_enabled.is_truthy()?)?;
        if let Some(notice) = notice {
            output.call_method1("print_stderr_line", (notice,))?;
        }
        arguments.push(("timings_ms", timings.clone().into_any()));
        arguments.push(("sql_validation_enabled", validation_enabled));
        PyString::new(
            py,
            &format_compile_json(py, Some(keywords(py, &arguments)?))?,
        )
    } else {
        let use_color: bool =
            !native_field(request, "no_color")?.is_truthy()? && stdout_supports_color(py)?;
        arguments.push((
            "use_color",
            PyBool::new(py, use_color).to_owned().into_any(),
        ));
        arguments.push(("sql_validation_enabled", validation_enabled));
        format_compile_text(py, Some(keywords(py, &arguments)?))?
    };
    output.call_method1("record_stdout", (rendered,))?;
    Ok(())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_compile_command, module)?)
}
