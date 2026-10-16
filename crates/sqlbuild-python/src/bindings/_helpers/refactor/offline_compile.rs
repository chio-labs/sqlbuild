//! Offline compiles that feed and verify a refactoring.

use std::path::Path;

use pyo3::IntoPyObject;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyBool, PyString};

use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::records::ids::{ErrorId, NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;

const DEFAULT_ERROR_CODE: &str = "E001";

/// One offline compile's project facts, or `None`, and every error that stopped or followed it.
pub(crate) struct OfflineCompile<'py> {
    pub(crate) project: Bound<'py, PyAny>,
    pub(crate) errors: Vec<Bound<'py, PyAny>>,
}

fn enum_member<'py>(py: Python<'py>, class: RecordId, member: &str) -> PyResult<Bound<'py, PyAny>> {
    registry::member(py, class, member)
}

fn matches_any_class(py: Python<'_>, error: &PyErr, classes: &[ErrorId]) -> PyResult<bool> {
    for class in classes {
        if error.value(py).is_instance(&registry::error(py, *class)?)? {
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
        &registry::class(py, RecordId::CompilerDiagnostic)?,
        &[
            (
                "phase",
                enum_member(py, RecordId::DiagnosticPhase, "COMPILE")?,
            ),
            (
                "severity",
                enum_member(py, RecordId::DiagnosticSeverity, "ERROR")?,
            ),
            ("code", code),
            ("message", message),
        ],
    )
}

/// A SQL-test planning failure as the test-phase error diagnostic it reports.
fn planning_error_diagnostic<'py>(py: Python<'py>, error: &PyErr) -> PyResult<Bound<'py, PyAny>> {
    let value: Bound<'py, PyAny> = error.value(py).clone().into_any();
    let location: Bound<'py, PyAny> =
        if value.is_instance(&registry::error(py, ErrorId::SqlTestReference)?)? {
            value.getattr("location")?
        } else {
            py.None().into_bound(py)
        };
    call_with(
        &registry::class(py, RecordId::CompilerDiagnostic)?,
        &[
            ("phase", enum_member(py, RecordId::DiagnosticPhase, "TEST")?),
            (
                "severity",
                enum_member(py, RecordId::DiagnosticSeverity, "ERROR")?,
            ),
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
        &registry::class(py, RecordId::CompileAnalysisSelection)?,
        &[("no_cache", PyBool::new(py, no_cache).to_owned().into_any())],
    )?;
    call_with(
        &registry::native(py, NativeAttr::AnalyzeCompileProject)?,
        &[
            ("project_dir", project_dir.into_pyobject(py)?.into_any()),
            (
                "no_sql_validation",
                PyBool::new(py, false).to_owned().into_any(),
            ),
            ("selected_target", py.None().into_bound(py)),
            (
                "lineage_mode",
                registry::class(py, RecordId::CompileLineageMode)?.getattr("NONE")?,
            ),
            ("cli_vars", py.None().into_bound(py)),
            (
                "profile_flags",
                registry::class(py, RecordId::CompileProfileFlags)?.call0()?,
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
            if error.is_instance_of::<PyValueError>(py)
                || matches_any_class(py, &error, &[ErrorId::Rules, ErrorId::SpecConfig])? =>
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
            &registry::native(py, NativeAttr::StaticSqlTestPlanningDiagnostics)?,
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
                    &[ErrorId::CompileInput, ErrorId::PlannerInput],
                )? =>
            {
                errors.push(planning_error_diagnostic(py, &error)?);
            }
            Err(error) => return Err(error),
        }
    }
    let project: Bound<'py, PyAny> = call_with(
        &registry::class(py, RecordId::RefactorProject)?,
        &[
            ("project_dir", project_dir.into_pyobject(py)?.into_any()),
            ("graph", analysis.getattr("graph")?),
            ("discovered", analysis.getattr("discovered_inputs")?),
        ],
    )?;
    Ok(OfflineCompile { project, errors })
}
