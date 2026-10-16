//! Materialize native plan rows as the existing executor-facing dataclasses.

use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::records::ids::RecordId;
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::sql_test_glue::planning::{AssertionRow, ChainRow, PlanRow};
use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyTuple;

fn chain_step<'py>(py: Python<'py>, row: ChainRow) -> PyResult<Bound<'py, PyAny>> {
    let (model, sql, expected_sql, lifted, body, expected_columns, expected_lifted) = row;
    call_with(
        &registry::class(py, RecordId::ChainStep)?,
        &[
            ("model_name", model.into_bound_py_any(py)?),
            ("resolved_sql", sql.into_bound_py_any(py)?),
            ("expected_cte_sql", expected_sql.into_bound_py_any(py)?),
            ("lifted_ctes", PyTuple::new(py, lifted)?.into_any()),
            ("comparison_body_sql", body.into_bound_py_any(py)?),
            (
                "expected_columns",
                match expected_columns {
                    Some(columns) => PyTuple::new(py, columns)?.into_any(),
                    None => py.None().into_bound(py),
                },
            ),
            (
                "expected_lifted_ctes",
                PyTuple::new(py, expected_lifted)?.into_any(),
            ),
        ],
    )
}

fn assertion_step<'py>(py: Python<'py>, row: AssertionRow) -> PyResult<Bound<'py, PyAny>> {
    let (name, sql, lifted, body) = row;
    call_with(
        &registry::class(py, RecordId::SqlTestAssertionStep)?,
        &[
            ("name", name.into_bound_py_any(py)?),
            ("resolved_sql", sql.into_bound_py_any(py)?),
            ("lifted_ctes", PyTuple::new(py, lifted)?.into_any()),
            ("comparison_body_sql", body.into_bound_py_any(py)?),
        ],
    )
}

pub(super) fn plan(py: Python<'_>, row: PlanRow) -> PyResult<Bound<'_, PyAny>> {
    let (sql, chain_rows, assertion_rows, model_names, warning_rows, error_messages) = row;
    let mut chain: Vec<Bound<'_, PyAny>> = Vec::new();
    for value in chain_rows {
        chain.push(chain_step(py, value)?);
    }
    let mut assertions: Vec<Bound<'_, PyAny>> = Vec::new();
    for value in assertion_rows {
        assertions.push(assertion_step(py, value)?);
    }
    let mut warnings: Vec<Bound<'_, PyAny>> = Vec::new();
    let severity = registry::class(py, RecordId::WarningSeverity)?;
    for (model_name, level, message) in warning_rows {
        warnings.push(call_with(
            &registry::class(py, RecordId::PlanWarning)?,
            &[
                ("model_name", model_name.into_bound_py_any(py)?),
                ("severity", severity.call1((level,))?),
                ("message", message.into_bound_py_any(py)?),
            ],
        )?);
    }
    call_with(
        &registry::class(py, RecordId::NativeSqlTestPlan)?,
        &[
            ("chain", PyTuple::new(py, chain)?.into_any()),
            ("assertions", PyTuple::new(py, assertions)?.into_any()),
            ("model_names", PyTuple::new(py, model_names)?.into_any()),
            ("warnings", PyTuple::new(py, warnings)?.into_any()),
            (
                "error_messages",
                PyTuple::new(py, error_messages)?.into_any(),
            ),
            ("sql", sql.into_bound_py_any(py)?),
        ],
    )
}
