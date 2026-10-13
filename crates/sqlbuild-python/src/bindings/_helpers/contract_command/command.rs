//! `sqb contract`: compare selected contracts with one target, optionally adopt them.

use std::time::Instant;

use pyo3::exceptions::{PyException, PyValueError};
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{
    PyBool, PyDict, PyDictMethods, PyFloat, PyInt, PyString, PyTuple, PyTupleMethods,
};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::contract_command::main::contract_exit_code::contract_exit_code;
use sqlbuild_core::contract_command::main::contract_progress_message::contract_progress_message;
use sqlbuild_core::contract_command::main::render_contract_json::render_contract_json;
use sqlbuild_core::contract_command::main::render_contract_text::render_contract_text;
use sqlbuild_core::contract_command::models::{
    ContractFindingText, ContractProgress, ContractReport, ContractResourceText,
};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

const NATIVE_MODULE: &str = "sqlbuild._native";
const ERRORS_MODULE: &str = "sqlbuild.cli.commands.exceptions";
const REJECT_UNIT_TESTS_MODULE: &str = "sqlbuild.compiler.pipeline.main.reject_unit_test_selectors";
const ADAPTER_CONTEXT_MODULE: &str = "sqlbuild.cli.commands._helpers.runtime.adapter_context";
const COMPILE_MODELS: &str = "sqlbuild.compiler.compile.models";
const GRAPH_SELECTION_MODULE: &str = "sqlbuild.compiler.pipeline.main.project_graph_selection";
const COLOR_MODULE: &str = "sqlbuild.presentation.main.supports_color";
const STATUS_REPORTER_MODULE: &str = "sqlbuild.presentation.classes.transient_status_reporter";
const ADOPTION_MODELS: &str = "sqlbuild.compiler.contract_adoption.models";
const WRITE_MODULE: &str = "sqlbuild.compiler.contract_adoption.main._write";
const GENERATE_ACTION: &str = "generate";

/// A `CliUserError` with its code.
fn user_error(py: Python<'_>, message: &str, code: &str) -> PyErr {
    let raised = (|| {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("code", code)?;
        imported(py, ERRORS_MODULE, "CliUserError")?.call((message,), Some(&options))
    })();
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

fn optional_text(value: Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_none() {
        return Ok(None);
    }
    Ok(Some(value.str()?.to_string()))
}

/// The selected graph, compiled against the source target, and its selected models and sources.
struct Selection<'py> {
    graph: Bound<'py, PyAny>,
    models: Bound<'py, PyTuple>,
    sources: Bound<'py, PyTuple>,
}

fn selected_of<'py>(
    resources: Bound<'py, PyAny>,
    selected: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let mut kept: Vec<Bound<'py, PyAny>> = Vec::new();
    for resource in resources.try_iter()? {
        let resource: Bound<'py, PyAny> = resource?;
        if selected.contains(resource.getattr("key")?)? {
            kept.push(resource);
        }
    }
    PyTuple::new(resources.py(), kept)
}

fn select_resources<'py>(
    request: &Bound<'py, PyAny>,
    discovered: &Bound<'py, PyAny>,
    context: &Bound<'py, PyAny>,
) -> PyResult<Selection<'py>> {
    let py: Python<'py> = request.py();
    let analysis: Bound<'py, PyAny> = call_with(
        &imported(py, COMPILE_MODELS, "CompileAnalysisSelection")?,
        &[("no_cache", PyBool::new(py, true).to_owned().into_any())],
    )?;
    let project: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "build_compiled_project")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("adapter", context.getattr("adapter")?),
            ("selected_target", request.getattr("from_target")?),
            ("cli_vars", request.getattr("cli_vars")?),
            ("resolved_connection", context.getattr("connection_config")?),
            ("analysis_selection", analysis),
        ],
    )?;
    let graph: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            NATIVE_MODULE,
            "build_project_graph_from_compiled_project",
        )?,
        &[("project", project)],
    )?;
    let selected: Bound<'py, PyAny> = call_with(
        &imported(py, GRAPH_SELECTION_MODULE, "select_project_graph")?,
        &[
            ("graph", graph.clone()),
            ("select", request.getattr("select")?),
            ("exclude", request.getattr("exclude")?),
        ],
    )?;
    let compiled: Bound<'py, PyAny> = graph.getattr("project")?;
    let models: Bound<'py, PyTuple> = selected_of(compiled.getattr("models")?, &selected)?;
    let sources: Bound<'py, PyTuple> = selected_of(compiled.getattr("sources")?, &selected)?;
    if models.is_empty() && sources.is_empty() {
        return Err(user_error(
            py,
            "contract selection contains no models or sources",
            "C473",
        ));
    }
    Ok(Selection {
        graph,
        models,
        sources,
    })
}

/// Where progress goes and whether it is coloured.
struct Progress<'py> {
    stream: Bound<'py, PyAny>,
    use_color: bool,
}

impl<'py> Progress<'py> {
    fn status(&self) -> PyResult<Bound<'py, PyAny>> {
        let py: Python<'py> = self.stream.py();
        call_with(
            &imported(py, STATUS_REPORTER_MODULE, "TransientStatusReporter")?,
            &[
                ("stream", self.stream.clone()),
                (
                    "use_color",
                    PyBool::new(py, self.use_color).to_owned().into_any(),
                ),
            ],
        )
    }
}

fn exception(py: Python<'_>, error: &PyErr) -> bool {
    error.is_instance_of::<PyException>(py)
}

fn connection_timing(reporter: &Bound<'_, PyAny>, method: &str, started: Instant) -> PyResult<()> {
    let py: Python<'_> = reporter.py();
    call_with(
        &reporter.getattr(method)?,
        &[
            ("connection_count", PyInt::new(py, 1).into_any()),
            (
                "elapsed_seconds",
                PyFloat::new(py, started.elapsed().as_secs_f64()).into_any(),
            ),
        ],
    )?;
    Ok(())
}

/// Compare the selected contracts over one connection that is always closed.
fn compare<'py>(
    request: &Bound<'py, PyAny>,
    context: &Bound<'py, PyAny>,
    selection: &Selection<'py>,
    progress: &Progress<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let adapter: Bound<'py, PyAny> = context.getattr("adapter")?;
    let reporter: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "ConnectionProgressReporter")?,
        &[
            ("adapter_name", context.getattr("adapter_name")?),
            ("stream", progress.stream.clone()),
            (
                "use_color",
                PyBool::new(py, progress.use_color).to_owned().into_any(),
            ),
        ],
    )?;
    let connection_started: Instant = Instant::now();
    reporter.call_method1("on_connection_start", (1,))?;
    let connection: Bound<'py, PyAny> =
        match adapter.call_method1("connect", (context.getattr("connection_config")?,)) {
            Ok(connection) => connection,
            Err(error) => {
                if exception(py, &error) {
                    connection_timing(&reporter, "on_connection_error", connection_started)?;
                }
                return Err(error);
            }
        };
    let compared: PyResult<Bound<'py, PyAny>> = (|| {
        connection_timing(&reporter, "on_connection_complete", connection_started)?;
        let count: usize = selection.models.len() + selection.sources.len();
        let target: String = request.getattr("from_target")?.str()?.to_string();
        let status: Bound<'py, PyAny> = progress.status()?;
        let started: Instant = Instant::now();
        status.call_method1(
            "start",
            (contract_progress_message(
                &ContractProgress::InspectionStart {
                    count,
                    target: target.clone(),
                },
            ),),
        )?;
        let evidence: Bound<'py, PyAny> = match call_with(
            &imported(py, NATIVE_MODULE, "compare_contracts")?,
            &[
                ("adapter", adapter.clone()),
                ("connection", connection.clone()),
                ("models", selection.models.clone().into_any()),
                ("sources", selection.sources.clone().into_any()),
            ],
        ) {
            Ok(evidence) => evidence,
            Err(error) => {
                if exception(py, &error) {
                    status.call_method1(
                        "error",
                        (contract_progress_message(
                            &ContractProgress::InspectionFailed {
                                seconds: started.elapsed().as_secs_f64(),
                            },
                        ),),
                    )?;
                }
                return Err(error);
            }
        };
        let options: Bound<'py, PyDict> = PyDict::new(py);
        options.set_item(
            "message",
            contract_progress_message(&ContractProgress::InspectionComplete {
                count,
                target,
                seconds: started.elapsed().as_secs_f64(),
            }),
        )?;
        status.call_method("complete", (), Some(&options))?;
        Ok(evidence)
    })();
    let closed: PyResult<Bound<'py, PyAny>> = adapter.call_method1("close", (connection,));
    let evidence: Bound<'py, PyAny> = compared?;
    closed?;
    Ok(evidence)
}

/// Write the adopted declarations into the repository and report the files written.
fn write_updates<'py>(
    request: &Bound<'py, PyAny>,
    (project_dir, context): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (graph, result): (&Bound<'py, PyAny>, Bound<'py, PyAny>),
    progress: &Progress<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let status: Bound<'py, PyAny> = progress.status()?;
    let started: Instant = Instant::now();
    status.call_method1("start", ("Updating repository contracts...",))?;
    let updated: Bound<'py, PyAny> = match call_with(
        &imported(py, WRITE_MODULE, "write_contracts")?,
        &[
            ("project_dir", project_dir.clone()),
            ("graph", graph.clone()),
            ("result", result),
            ("overwrite", request.getattr("overwrite")?),
            ("adapter", context.getattr("adapter")?),
            ("resolved_connection", context.getattr("connection_config")?),
            ("cli_vars", request.getattr("cli_vars")?),
        ],
    ) {
        Ok(updated) => updated,
        Err(error) => {
            if exception(py, &error) {
                status.call_method1(
                    "error",
                    (contract_progress_message(&ContractProgress::WriteFailed {
                        seconds: started.elapsed().as_secs_f64(),
                    }),),
                )?;
            }
            return Err(error);
        }
    };
    let written: usize = updated.getattr("written_paths")?.len()?;
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item(
        "message",
        contract_progress_message(&ContractProgress::WriteComplete {
            count: written,
            seconds: started.elapsed().as_secs_f64(),
        }),
    )?;
    status.call_method("complete", (), Some(&options))?;
    Ok(updated)
}

fn finding_text(finding: Bound<'_, PyAny>) -> PyResult<ContractFindingText> {
    Ok(ContractFindingText {
        kind: finding.getattr("kind")?.str()?.to_string(),
        column: optional_text(finding.getattr("column_name")?)?,
        declared_type: optional_text(finding.getattr("declared_type")?)?,
        physical_type: optional_text(finding.getattr("physical_type")?)?,
        message: finding.getattr("message")?.str()?.to_string(),
    })
}

fn resource_text(item: Bound<'_, PyAny>) -> PyResult<ContractResourceText> {
    let mut parts: Vec<String> = Vec::new();
    for field in ["database", "schema", "relation"] {
        let value: Bound<'_, PyAny> = item.getattr(field)?;
        if value.is_truthy()? {
            parts.push(value.str()?.to_string());
        }
    }
    Ok(ContractResourceText {
        resource_type: item.getattr("resource_type")?.str()?.to_string(),
        resource_name: item.getattr("resource_name")?.str()?.to_string(),
        relation: parts.join("."),
        findings: item
            .getattr("findings")?
            .try_iter()?
            .map(|finding| finding_text(finding?))
            .collect::<PyResult<_>>()?,
    })
}

fn report(result: &Bound<'_, PyAny>) -> PyResult<ContractReport> {
    Ok(ContractReport {
        from_target: result.getattr("from_target")?.str()?.to_string(),
        resources: result
            .getattr("evidence")?
            .try_iter()?
            .map(|item| resource_text(item?))
            .collect::<PyResult<_>>()?,
        written_paths: result
            .getattr("written_paths")?
            .try_iter()?
            .map(|path| Ok(path?.str()?.to_string()))
            .collect::<PyResult<_>>()?,
    })
}

fn progress_for<'py>(request: &Bound<'py, PyAny>) -> PyResult<Progress<'py>> {
    let py: Python<'py> = request.py();
    let json_output: bool = request.getattr("json_output")?.is_truthy()?;
    let stream: Bound<'py, PyAny> =
        py.import("sys")?
            .getattr(if json_output { "stderr" } else { "stdout" })?;
    let use_color: bool = !request.getattr("no_color")?.is_truthy()?
        && !json_output
        && imported(py, COLOR_MODULE, "supports_color")?
            .call0()?
            .is_truthy()?;
    Ok(Progress { stream, use_color })
}

/// Compare or adopt selected contracts from one read-only target.
#[pyfunction]
#[pyo3(signature = (*, request))]
fn run_contract_command(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let action: String = request.getattr("action")?.str()?.to_string();
    let generate_write: bool =
        action == GENERATE_ACTION && request.getattr("write")?.is_truthy()?;
    if request.getattr("overwrite")?.is_truthy()? && !generate_write {
        return Err(user_error(
            py,
            "contract --overwrite requires generate --write",
            "C471",
        ));
    }
    let requested_dir: Bound<'_, PyAny> = request.getattr("project_dir")?;
    let project_dir: Bound<'_, PyAny> = if requested_dir.is_truthy()? {
        requested_dir
    } else {
        imported(py, "pathlib", "Path")?.call_method0("cwd")?
    };
    let discovered: Bound<'_, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "discover_project_inputs")?,
        &[("project_dir", project_dir.clone())],
    )?;
    call_with(
        &imported(py, REJECT_UNIT_TESTS_MODULE, "reject_unit_test_selectors")?,
        &[
            ("select", request.getattr("select")?),
            ("exclude", request.getattr("exclude")?),
            ("discovered_inputs", discovered.clone()),
        ],
    )?;
    let from_target: Bound<'_, PyAny> = request.getattr("from_target")?;
    if !discovered
        .getattr("project_config")?
        .getattr("targets")?
        .contains(&from_target)?
    {
        return Err(user_error(
            py,
            &format!("unknown contract source target '{}'", from_target.str()?),
            "C472",
        ));
    }
    let context: Bound<'_, PyAny> = call_with(
        &imported(
            py,
            ADAPTER_CONTEXT_MODULE,
            "resolve_adapter_connection_context",
        )?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("effective_project_dir", project_dir.clone()),
            ("selected_target", py.None().into_bound(py)),
            ("cli_vars", request.getattr("cli_vars")?),
        ],
    )?;
    let selection: Selection<'_> = select_resources(request, &discovered, &context)?;
    let progress: Progress<'_> = progress_for(request)?;
    let evidence: Bound<'_, PyAny> = compare(request, &context, &selection, &progress)?;
    let mut result: Bound<'_, PyAny> = call_with(
        &imported(py, ADOPTION_MODELS, "ContractAdoptionResult")?,
        &[("from_target", from_target), ("evidence", evidence)],
    )?;
    if generate_write {
        result = write_updates(
            request,
            (&project_dir, &context),
            (&selection.graph, result),
            &progress,
        )?;
    }
    let report: ContractReport = report(&result)?;
    let rendered: String = if request.getattr("json_output")?.is_truthy()? {
        render_contract_json(&report)
            .map_err(|error| PyValueError::new_err(format!("{error:?}")))?
    } else {
        render_contract_text(&report)
    };
    py.import("sys")?
        .getattr("stdout")?
        .call_method1("write", (PyString::new(py, &rendered),))?;
    Ok(contract_exit_code(report.difference_count()))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_contract_command, module)?)?;
    Ok(())
}
