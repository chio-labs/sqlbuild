//! Compile's explicit-reference checks over plain project facts, run natively.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use serde_json::{Value, json};
use sqlbuild_analysis::explicit_references::errors::ReferenceFailure;
use sqlbuild_analysis::explicit_references::main::check_explicit_references::check_explicit_references;
use sqlbuild_analysis::explicit_references::models::{ReferenceReport, ReferenceRequest};
use sqlbuild_core::panics::main::native_failure::native_failure;

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::types::CompilerDetach;

const EXPLICIT_REFERENCES_CONTEXT: &str = "native explicit-reference checks";

/// Python's audit-gate, hook-read and Python-SQL checks: `{report}` or `{raise}` JSON.
#[pyfunction]
fn check_native_explicit_references(py: Python<'_>, request_json: &str) -> PyResult<String> {
    let request: ReferenceRequest = serde_json::from_str(request_json).map_err(|error| {
        compiler_error(native_failure(
            EXPLICIT_REFERENCES_CONTEXT,
            &error.to_string(),
        ))
    })?;
    let outcome: Value = match py
        .compiler_detach(|| Ok(check_explicit_references(&request)))
        .map_err(compiler_error)?
    {
        Ok(report) => json!({ "report": report_value(&report)? }),
        Err(ReferenceFailure::CompileInput(message)) => json!({ "raise": message }),
        Err(ReferenceFailure::UnknownDialect(message)) => return Err(compiler_error(message)),
        Err(ReferenceFailure::Internal(reason)) => {
            return Err(compiler_error(native_failure(
                EXPLICIT_REFERENCES_CONTEXT,
                &reason,
            )));
        }
    };
    serde_json::to_string(&outcome).map_err(|error| {
        compiler_error(native_failure(
            EXPLICIT_REFERENCES_CONTEXT,
            &error.to_string(),
        ))
    })
}

fn report_value(report: &ReferenceReport) -> PyResult<Value> {
    serde_json::to_value(report).map_err(|error| {
        compiler_error(native_failure(
            EXPLICIT_REFERENCES_CONTEXT,
            &error.to_string(),
        ))
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(check_native_explicit_references, module)?)?;
    Ok(())
}
