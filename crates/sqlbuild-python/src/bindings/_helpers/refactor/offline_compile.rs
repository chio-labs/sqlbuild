//! Offline compiles that feed and verify a refactoring.

use std::path::Path;

use crate::bindings::_helpers::compiler_records::shape_classes::shape_class_at;
use pyo3::IntoPyObject;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyBool, PyString};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const NATIVE_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS: &str = "sqlbuild.compiler.compile.models";
const COMPILE_TYPES: &str = "sqlbuild.compiler.compile.types";
const COMPILE_ERRORS: &str = "sqlbuild._native";
const PLANNER_ERRORS: &str = "sqlbuild._native";
const RULES_ERRORS: &str = "sqlbuild._native";
const SPEC_ERRORS: &str = "sqlbuild._native";
const ENTRY_MODELS: &str = "sqlbuild._native";
const COMMAND_TYPES: &str = "sqlbuild._native";
const REFACTOR_MODELS: &str = "sqlbuild._native";
const DEFAULT_ERROR_CODE: &str = "E001";

/// One offline compile's project facts, or `None`, and every error that stopped or followed it.
pub(crate) struct OfflineCompile<'py> {
    pub(crate) project: Bound<'py, PyAny>,
    pub(crate) errors: Vec<Bound<'py, PyAny>>,
}

fn enum_member<'py>(py: Python<'py>, class: &str, member: &str) -> PyResult<Bound<'py, PyAny>> {
    shape_class_at(py, COMPILE_TYPES, class)?.getattr(member)
}

fn matches_any_class(py: Python<'_>, error: &PyErr, classes: &[(&str, &str)]) -> PyResult<bool> {
    for (module, name) in classes {
        if error.value(py).is_instance(&imported(py, module, name)?)? {
            return Ok(true);
        }
    }
    Ok(false)
}

/// A compile failure as the one error diagnostic it reports.
fn compile_error_diagnostic<'py>(py: Python<'py>, error: &PyErr) -> PyResult<Bound<'py, PyAny>> {
    let value: Bound<'py, PyAny> = error.value(py).clone().into_any();
    let code: Bound<'py, PyAny> = if value.hasattr("code")? {
        value.getattr("code")?.str()?.into_any()
    } else {
        PyString::new(py, DEFAULT_ERROR_CODE).into_any()
    };
    let message: Bound<'py, PyAny> = if value.hasattr("message")? {
        value.getattr("message")?.str()?.into_any()
    } else {
        value.str()?.into_any()
    };
    call_with(
        &imported(py, COMPILE_MODELS, "CompilerDiagnostic")?,
        &[
            ("phase", enum_member(py, "DiagnosticPhase", "COMPILE")?),
            ("severity", enum_member(py, "DiagnosticSeverity", "ERROR")?),
            ("code", code),
            ("message", message),
        ],
    )
}

/// A SQL-test planning failure as the test-phase error diagnostic it reports.
fn planning_error_diagnostic<'py>(py: Python<'py>, error: &PyErr) -> PyResult<Bound<'py, PyAny>> {
    let value: Bound<'py, PyAny> = error.value(py).clone().into_any();
    let location: Bound<'py, PyAny> =
        if value.is_instance(&imported(py, COMPILE_ERRORS, "SqlTestReferenceError")?)? {
            value.getattr("location")?
        } else {
            py.None().into_bound(py)
        };
    call_with(
        &imported(py, COMPILE_MODELS, "CompilerDiagnostic")?,
        &[
            ("phase", enum_member(py, "DiagnosticPhase", "TEST")?),
            ("severity", enum_member(py, "DiagnosticSeverity", "ERROR")?),
            ("code", value.getattr("code")?),
            ("message", value.str()?.into_any()),
            ("help", value.getattr("help")?),
            ("location", location),
        ],
    )
}

fn error_diagnostics<'py>(diagnostics: Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut errors: Vec<Bound<'py, PyAny>> = Vec::new();
    for diagnostic in diagnostics.try_iter()? {
        let diagnostic: Bound<'py, PyAny> = diagnostic?;
        if diagnostic.getattr("is_error")?.is_truthy()? {
            errors.push(diagnostic);
        }
    }
    Ok(errors)
}

fn analyzed<'py>(
    py: Python<'py>,
    project_dir: &Path,
    no_cache: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let selection: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_RECORDS_MODULE, "CompileAnalysisSelection")?,
        &[("no_cache", PyBool::new(py, no_cache).to_owned().into_any())],
    )?;
    call_with(
        &imported(py, NATIVE_MODULE, "analyze_compile_project")?,
        &[
            ("project_dir", project_dir.into_pyobject(py)?.into_any()),
            (
                "no_sql_validation",
                PyBool::new(py, false).to_owned().into_any(),
            ),
            ("selected_target", py.None().into_bound(py)),
            (
                "lineage_mode",
                imported(py, COMMAND_TYPES, "CompileLineageMode")?.getattr("NONE")?,
            ),
            ("cli_vars", py.None().into_bound(py)),
            (
                "profile_flags",
                imported(py, ENTRY_MODELS, "CompileProfileFlags")?.call0()?,
            ),
            ("analysis_selection", selection),
            ("status", py.None().into_bound(py)),
        ],
    )
}

/// Compile a project the way `sqb compile` does and collect every error.
pub(crate) fn compile_for_refactor<'py>(
    py: Python<'py>,
    project_dir: &Path,
    no_cache: bool,
) -> PyResult<OfflineCompile<'py>> {
    let analysis: Bound<'py, PyAny> = match analyzed(py, project_dir, no_cache) {
        Ok(analysis) => analysis,
        Err(error)
            if matches_any_class(
                py,
                &error,
                &[
                    ("builtins", "ValueError"),
                    (RULES_ERRORS, "RulesError"),
                    (SPEC_ERRORS, "SpecConfigError"),
                ],
            )? =>
        {
            return Ok(OfflineCompile {
                project: py.None().into_bound(py),
                errors: vec![compile_error_diagnostic(py, &error)?],
            });
        }
        Err(error) => return Err(error),
    };
    let mut errors: Vec<Bound<'py, PyAny>> = error_diagnostics(analysis.getattr("diagnostics")?)?;
    if errors.is_empty() {
        let planned: PyResult<Bound<'py, PyAny>> = call_with(
            &imported(py, NATIVE_MODULE, "static_sql_test_planning_diagnostics")?,
            &[
                (
                    "target_dir",
                    project_dir.join("target").into_pyobject(py)?.into_any(),
                ),
                ("adapter", analysis.getattr("adapter")?),
                ("project", analysis.getattr("graph")?.getattr("project")?),
            ],
        );
        match planned {
            Ok(diagnostics) => errors.extend(error_diagnostics(diagnostics)?),
            Err(error)
                if matches_any_class(
                    py,
                    &error,
                    &[
                        (COMPILE_ERRORS, "CompileInputError"),
                        (PLANNER_ERRORS, "PlannerInputError"),
                    ],
                )? =>
            {
                errors.push(planning_error_diagnostic(py, &error)?);
            }
            Err(error) => return Err(error),
        }
    }
    let project: Bound<'py, PyAny> = call_with(
        &imported(py, REFACTOR_MODELS, "RefactorProject")?,
        &[
            ("project_dir", project_dir.into_pyobject(py)?.into_any()),
            ("graph", analysis.getattr("graph")?),
            ("discovered", analysis.getattr("discovered_inputs")?),
        ],
    )?;
    Ok(OfflineCompile { project, errors })
}
