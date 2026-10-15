//! Materialize native plan rows as the existing executor-facing dataclasses.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::compiler_records::shape_classes::shape_class_at;
use crate::bindings::_helpers::sql_test_glue::constants::PLAN_MODELS;
use crate::bindings::_helpers::sql_test_glue::plan_values::tuple;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};

fn step<'py>(row: &Bound<'py, PyAny>, chain: bool) -> PyResult<Bound<'py, PyAny>> {
    let py = row.py();
    let kwargs = PyDict::new(py);
    let fields: &[&str] = if chain {
        &[
            "model_name",
            "resolved_sql",
            "expected_cte_sql",
            "lifted_ctes",
            "comparison_body_sql",
            "expected_columns",
            "expected_lifted_ctes",
        ]
    } else {
        &["name", "resolved_sql", "lifted_ctes", "comparison_body_sql"]
    };
    for (index, name) in fields.iter().enumerate() {
        let value = row.get_item(index)?;
        kwargs.set_item(
            *name,
            if ["lifted_ctes", "expected_columns", "expected_lifted_ctes"].contains(name)
                && !value.is_none()
            {
                tuple(&value)?
            } else {
                value
            },
        )?;
    }
    shape_class_at(
        py,
        PLAN_MODELS,
        if chain {
            "ChainStep"
        } else {
            "SqlTestAssertionStep"
        },
    )?
    .call((), Some(&kwargs))
}

pub(super) fn plan<'py>(row: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py = row.py();
    let mut chain: Vec<Bound<'py, PyAny>> = Vec::new();
    for value in row.get_item(1)?.try_iter()? {
        chain.push(step(&value?, true)?);
    }
    let mut assertions: Vec<Bound<'py, PyAny>> = Vec::new();
    for value in row.get_item(2)?.try_iter()? {
        assertions.push(step(&value?, false)?);
    }
    let mut warnings: Vec<Bound<'py, PyAny>> = Vec::new();
    let severity = imported(py, "sqlbuild._native", "WarningSeverity")?;
    for value in row.get_item(4)?.try_iter()? {
        let value = value?;
        warnings.push(call_with(
            &imported(py, "sqlbuild._native", "PlanWarning")?,
            &[
                ("model_name", value.get_item(0)?),
                ("severity", severity.call1((value.get_item(1)?,))?),
                ("message", value.get_item(2)?),
            ],
        )?);
    }
    call_with(
        &imported(py, "sqlbuild._native", "NativeSqlTestPlan")?,
        &[
            ("chain", PyTuple::new(py, chain)?.into_any()),
            ("assertions", PyTuple::new(py, assertions)?.into_any()),
            ("model_names", tuple(&row.get_item(3)?)?),
            ("warnings", PyTuple::new(py, warnings)?.into_any()),
            ("error_messages", tuple(&row.get_item(5)?)?),
            ("sql", row.get_item(0)?),
        ],
    )
}
