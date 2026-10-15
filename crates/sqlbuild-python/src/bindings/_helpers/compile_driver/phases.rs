//! The compile output phases: manifest, DAG artifact, compiled artifacts and withheld test errors.

use pyo3::IntoPyObject;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyTuple;

use crate::bindings::_helpers::compile_command::artifact_batch::ArtifactBatch;
use crate::bindings::_helpers::compile_command::reuse_recording::ArtifactRecorder;
use crate::bindings::_helpers::compile_command::target_writer::{
    Prepared, planning_diagnostics, write_static_target,
};
use crate::bindings::_helpers::compile_driver::python_calls::{Status, call_with, imported};
use crate::bindings::_helpers::dag_artifact::artifact::build_dag_json;
use crate::bindings::_helpers::graph::python_node_graph::python_node_graph;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const NATIVE_MODULE: &str = "sqlbuild._native";
const ADAPTER_NAME_MODULE: &str = "sqlbuild._native";
const OUTPUT_MODELS_MODULE: &str = "sqlbuild._native";
const COMPILE_EXCEPTIONS_MODULE: &str = "sqlbuild.compiler.compile.exceptions";
const PLANNER_EXCEPTIONS_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const EMPTY_DAG_PATH: &str = "";
const TARGET_DIRECTORY: &str = "target";
const DEFAULT_DAG_FILE: &str = "sqlbuild_dag.json";

/// Seconds since a `time.monotonic()` reading, formatted `{:.2f}`.
fn seconds_since(py: Python<'_>, started: f64) -> PyResult<String> {
    let now: f64 = imported(py, "time", "monotonic")?.call0()?.extract()?;
    Ok(format!("{:.2}", now - started))
}

/// A `time.monotonic()` reading.
pub(crate) fn monotonic(py: Python<'_>) -> PyResult<f64> {
    imported(py, "time", "monotonic")?.call0()?.extract()
}

/// Milliseconds since a `time.monotonic()` reading, truncated as `int(... * 1000)`.
pub(crate) fn elapsed_ms(py: Python<'_>, started: f64) -> PyResult<i64> {
    Ok(((monotonic(py)? - started) * 1000.0) as i64)
}

/// `project_dir / "target"`.
pub(crate) fn target_dir<'py>(project_dir: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    project_dir.call_method1("__truediv__", (TARGET_DIRECTORY,))
}

/// The manifest payload, when requested.
pub(crate) fn manifest_payload<'py>(
    requested: bool,
    analysis: &Bound<'py, PyAny>,
    status: &Status<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = analysis.py();
    if !requested {
        return Ok(py.None().into_bound(py));
    }
    let started: f64 = monotonic(py)?;
    status.start("Building manifest...")?;
    let discovered: Bound<'py, PyAny> = analysis.getattr("discovered_inputs")?;
    let project_config: Bound<'py, PyAny> = discovered.getattr("project_config")?;
    let graph: Bound<'py, PyAny> = analysis.getattr("graph")?;
    let adapter_type: Bound<'py, PyAny> = call_with(
        &imported(py, ADAPTER_NAME_MODULE, "resolve_effective_adapter_name")?,
        &[
            ("project_config", project_config.clone()),
            ("local_config", discovered.getattr("local_config")?),
        ],
    )?;
    let payload: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "build_manifest")?,
        &[
            ("project", graph.getattr("project")?),
            ("plan_output", py.None().into_bound(py)),
            ("project_name", project_config.getattr("name")?),
            ("adapter_type", adapter_type),
            ("graph", graph.getattr("native")?),
        ],
    )?;
    status.complete(&format!(
        "Built manifest. ({}s)",
        seconds_since(py, started)?
    ))?;
    Ok(payload)
}

/// The DAG artifact path a `--dag` value names, resolved against the project.
pub(crate) fn resolved_dag_path<'py>(
    project_dir: &Bound<'py, PyAny>,
    dag_path: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_dir.py();
    if dag_path.eq(EMPTY_DAG_PATH)? {
        return target_dir(project_dir)?.call_method1("__truediv__", (DEFAULT_DAG_FILE,));
    }
    let path: Bound<'py, PyAny> = imported(py, "pathlib", "Path")?.call1((dag_path,))?;
    if path.call_method0("is_absolute")?.is_truthy()? {
        return Ok(path);
    }
    project_dir.call_method1("__truediv__", (path,))
}

/// Write the DAG JSON artifact when a DAG path is requested.
pub(crate) fn write_dag_artifact<'py>(
    (dag_path, project_dir): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (analysis, recorder): (&Bound<'py, PyAny>, ArtifactRecorder<'_>),
    status: &Status<'py>,
) -> PyResult<()> {
    if dag_path.is_none() {
        return Ok(());
    }
    let py: Python<'py> = analysis.py();
    let started: f64 = monotonic(py)?;
    status.start("Writing DAG artifact...")?;
    let discovered: Bound<'py, PyAny> = analysis.getattr("discovered_inputs")?;
    let python_graph: Bound<'py, PyAny> = python_node_graph(&discovered)?;
    let path: Bound<'py, PyAny> = resolved_dag_path(project_dir, dag_path)?;
    let project_name: String = discovered
        .getattr("project_config")?
        .getattr("name")?
        .extract()?;
    let dag_json: String = build_dag_json(
        &analysis.getattr("graph")?,
        &project_name,
        Some(&python_graph),
    )?;
    let mut batch: ArtifactBatch = ArtifactBatch::new(false, recorder);
    batch.queue(&path, dag_json.into_bytes())?;
    batch.flush(py)?;
    status.complete(&format!(
        "Wrote DAG artifact. ({}s)",
        seconds_since(py, started)?
    ))
}

/// SQL test planning errors of a compile whose artifacts are withheld, reusing staged planning.
pub(crate) fn sql_test_planning_diagnostics<'py>(
    project_dir: &Bound<'py, PyAny>,
    analysis: &Bound<'py, PyAny>,
    (prepared_artifacts, recorder): (&Bound<'py, PyAny>, ArtifactRecorder<'_>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = analysis.py();
    let planned: PyResult<Bound<'py, PyAny>> = (|| {
        if !prepared_artifacts.is_none() {
            let staged: Bound<'py, PyAny> =
                prepared_artifacts.call_method0("planning_diagnostics")?;
            if !staged.is_none() {
                return Ok(staged);
            }
        }
        Ok(planning_diagnostics(
            &target_dir(project_dir)?,
            (
                &analysis.getattr("adapter")?,
                &analysis.getattr("graph")?.getattr("project")?,
            ),
            Prepared {
                planned_tests: None,
                recorder,
            },
        )?
        .into_any())
    })();
    let error = match planned {
        Ok(diagnostics) => return Ok(diagnostics),
        Err(error) => error,
    };
    let compile_input_error: Bound<'py, PyAny> =
        imported(py, COMPILE_EXCEPTIONS_MODULE, "CompileInputError")?;
    let planner_input_error: Bound<'py, PyAny> =
        imported(py, PLANNER_EXCEPTIONS_MODULE, "PlannerInputError")?;
    let value: Bound<'py, PyAny> = error.value(py).clone().into_any();
    if !(value.is_instance(&compile_input_error)? || value.is_instance(&planner_input_error)?) {
        return Err(error);
    }
    let reference_error: Bound<'py, PyAny> =
        imported(py, COMPILE_EXCEPTIONS_MODULE, "SqlTestReferenceError")?;
    let location: Bound<'py, PyAny> = if value.is_instance(&reference_error)? {
        value.getattr("location")?
    } else {
        py.None().into_bound(py)
    };
    let diagnostic: Bound<'py, PyAny> = call_with(
        &imported(py, COMPILE_MODELS_MODULE, "CompilerDiagnostic")?,
        &[
            (
                "phase",
                imported(py, NATIVE_RECORDS_MODULE, "DiagnosticPhase")?.getattr("TEST")?,
            ),
            (
                "severity",
                imported(py, NATIVE_RECORDS_MODULE, "DiagnosticSeverity")?.getattr("ERROR")?,
            ),
            ("code", value.getattr("code")?),
            ("message", value.str()?.into_any()),
            ("help", value.getattr("help")?),
            ("location", location),
        ],
    )?;
    Ok(PyTuple::new(py, [diagnostic])?.into_any())
}

/// Write compiled artifacts to `target/` and return `(written target, write milliseconds)`.
pub(crate) fn write_artifacts<'py>(
    (skip_write, project_dir): (bool, &Bound<'py, PyAny>),
    (analysis, manifest): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (prepared_artifacts, recorder): (&Bound<'py, PyAny>, ArtifactRecorder<'_>),
    status: &Status<'py>,
) -> PyResult<(Bound<'py, PyAny>, i64)> {
    let py: Python<'py> = analysis.py();
    let started: f64 = monotonic(py)?;
    let target: Bound<'py, PyAny> = target_dir(project_dir)?;
    let written: Bound<'py, PyAny> = if skip_write {
        let zero: Bound<'py, PyAny> = 0_i64.into_pyobject(py)?.into_any();
        call_with(
            &imported(py, OUTPUT_MODELS_MODULE, "WrittenTarget")?,
            &[
                ("model_count", zero.clone()),
                ("seed_count", zero.clone()),
                ("function_count", zero.clone()),
                ("audit_count", zero.clone()),
                ("test_count", zero),
                ("target_dir", target),
            ],
        )?
    } else {
        status.start("Writing compiled artifacts...")?;
        let staged: Bound<'py, PyAny> = if prepared_artifacts.is_none() {
            py.None().into_bound(py)
        } else {
            call_with(
                &prepared_artifacts.getattr("publish")?,
                &[
                    ("target_dir", target.clone()),
                    ("manifest", manifest.clone()),
                ],
            )?
        };
        if staged.is_none() {
            write_static_target(
                &target,
                (
                    &analysis.getattr("adapter")?,
                    &analysis.getattr("graph")?.getattr("project")?,
                ),
                manifest,
                Prepared {
                    planned_tests: None,
                    recorder,
                },
            )?
        } else {
            staged
        }
    };
    let write_ms: i64 = elapsed_ms(py, started)?;
    if !skip_write {
        status.complete(&format!(
            "Wrote compiled artifacts. ({:.2}s)",
            write_ms as f64 / 1000.0
        ))?;
    }
    Ok((written, write_ms))
}
