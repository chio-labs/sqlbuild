//! Every SQL test assembled natively; macro-mocked tests' model queries run the user's macros.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyList, PyTuple};

use crate::bindings::_helpers::boundary::panics::NativeCompilerError;
use crate::bindings::_helpers::compile_driver::assembly_checks::test_model_query_overrides;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};

const NATIVE_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const COMPILE_ERRORS_MODULE: &str = "sqlbuild.compiler.compile.exceptions";
const COLLECTOR_MODULE: &str = "sqlbuild._native";
const DECIMAL_MODULE: &str = "decimal";
const DATACLASSES_MODULE: &str = "dataclasses";
const SQL_TEST_INPUT_FAILURE: &str = "input";
const SQL_TEST_DECIMAL_OVERFLOW: &str = "decimal_overflow";

/// Every compiled SQL test, raising each assembly failure in the tests' order.
pub(crate) fn assembled_sql_tests<'py>(
    inputs: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = inputs.py();
    let assemblies: Vec<Bound<'py, PyAny>> = call_with(
        &imported(py, NATIVE_MODULE, "assemble_native_sql_tests")?,
        &[("inputs", inputs.clone())],
    )?
    .try_iter()?
    .collect::<PyResult<_>>()?;
    let test_inputs: Vec<Bound<'py, PyAny>> = inputs
        .getattr("test_inputs")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    if assemblies.len() != test_inputs.len() {
        return Err(NativeCompilerError::new_err(
            "native SQL test assembly returned a different number of tests",
        ));
    }
    let report: Bound<'py, PyAny> = imported(py, COLLECTOR_MODULE, "report_compile_diagnostic")?;
    let mocked_input: Bound<'py, PyAny> =
        imported(py, COMPILE_MODELS_MODULE, "CompileModelSqlTestInputPayload")?;
    let mut tests: Vec<Bound<'py, PyAny>> = Vec::with_capacity(assemblies.len());
    for (test_input, assembly) in test_inputs.iter().zip(assemblies) {
        let failure: Bound<'py, PyAny> = assembly.getattr("failure")?;
        let kind: Option<String> = if failure.is_none() {
            None
        } else {
            Some(failure.getattr("kind")?.extract()?)
        };
        let mut test: Bound<'py, PyAny> = assembly.getattr("test")?;
        if test.is_none() {
            return Err(assembly_error(py, &failure, kind.as_deref())?);
        }
        for item in assembly.getattr("diagnostics")?.try_iter()? {
            let (key, diagnostic): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
            call_with(&report, &[("key", key), ("diagnostic", diagnostic)])?;
        }
        let payload: Bound<'py, PyAny> = test_input.getattr("payload")?;
        if payload.is_instance(&mocked_input)? && payload.getattr("macro_mocks")?.is_truthy()? {
            test = with_model_queries(
                &test,
                test_model_query_overrides(test_input, inputs)?.as_any(),
            )?;
        }
        if kind.as_deref() == Some(SQL_TEST_DECIMAL_OVERFLOW) {
            let overflow: Bound<'py, PyAny> = imported(py, DECIMAL_MODULE, "Overflow")?;
            let raised: Bound<'py, PyAny> = overflow.call1((PyList::new(py, [&overflow])?,))?;
            return Err(PyErr::from_value(raised));
        }
        tests.push(test);
    }
    PyTuple::new(py, tests)
}

/// The failure of a test that did not assemble: input errors as `CompileInputError`.
fn assembly_error(
    py: Python<'_>,
    failure: &Bound<'_, PyAny>,
    kind: Option<&str>,
) -> PyResult<PyErr> {
    let message: String = if failure.is_none() {
        String::new()
    } else {
        failure.getattr("message")?.extract()?
    };
    if kind == Some(SQL_TEST_INPUT_FAILURE) {
        let error: Bound<'_, PyAny> =
            imported(py, COMPILE_ERRORS_MODULE, "CompileInputError")?.call1((message,))?;
        return Ok(PyErr::from_value(error));
    }
    Ok(NativeCompilerError::new_err(message))
}

/// `test` with its model payload's query overrides set to `queries`.
fn with_model_queries<'py>(
    test: &Bound<'py, PyAny>,
    queries: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = test.py();
    let payload: Bound<'py, PyAny> = test.getattr("payload")?;
    if !payload.is_instance(&imported(
        py,
        COMPILE_MODELS_MODULE,
        "CompiledModelSqlTestPayload",
    )?)? {
        return Ok(test.clone());
    }
    let replace: Bound<'py, PyAny> = imported(py, DATACLASSES_MODULE, "replace")?;
    let payload: Bound<'py, PyAny> = replace.call(
        (payload,),
        Some(&keywords(
            py,
            &[("model_query_overrides", queries.clone())],
        )?),
    )?;
    replace.call((test,), Some(&keywords(py, &[("payload", payload)])?))
}
