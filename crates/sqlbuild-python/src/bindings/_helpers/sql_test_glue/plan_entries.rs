//! Assemble existing SQL-test plan dataclasses without changing executor ownership.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyListMethods, PyTuple};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::sql_test_glue::constants::{COMPILE_TYPES, PLAN_MODELS};
use crate::bindings::_helpers::sql_test_glue::constants::{TABLE_FN, UDF};
use crate::bindings::_helpers::sql_test_glue::plan_values::model_payload;

use crate::bindings::_helpers::sql_test_glue::authored_ctes::prefixed_ctes;

fn prefixed_names<'py>(test: &Bound<'py, PyAny>, prefix: &str) -> PyResult<Bound<'py, PyAny>> {
    let py = test.py();
    let mut names: Vec<String> = if model_payload(test)? {
        prefixed_ctes(&test.getattr("payload")?.getattr("authored_ctes")?, prefix)?
            .keys()
            .extract()?
    } else {
        Vec::new()
    };
    names.sort();
    Ok(PyTuple::new(py, names)?.into_any())
}

fn function_deps<'py>(
    test: &Bound<'py, PyAny>,
    plan: &Bound<'py, PyAny>,
    project: &Bound<'py, PyAny>,
    inputs: (&Bound<'py, PyAny>, &Bound<'py, PyDict>),
) -> PyResult<Bound<'py, PyAny>> {
    let py = test.py();
    let deps = PyDict::new(py);
    if model_payload(test)? {
        let names: Vec<String> = plan.getattr("model_names")?.extract()?;
        let mocked: std::collections::HashSet<String> =
            inputs.0.extract::<Vec<String>>()?.into_iter().collect();
        let models = inputs.1;
        for name in names {
            let Some(model) = models.get_item(name)? else {
                continue;
            };
            for dep in model.getattr("deps")?.try_iter()? {
                let dep = dep?;
                let resource: String = dep.getattr("resource_type")?.getattr("value")?.extract()?;
                if resource != UDF && resource != TABLE_FN {
                    continue;
                }
                if resource == TABLE_FN
                    && mocked.contains(&dep.getattr("name")?.extract::<String>()?)
                {
                    continue;
                }
                deps.set_item(dep, py.None())?;
            }
        }
    } else {
        let payload = test.getattr("payload")?;
        let mode: String = payload.getattr("mode")?.getattr("value")?.extract()?;
        if mode == UDF || mode == TABLE_FN {
            let names: std::collections::HashSet<String> = payload
                .getattr("tested_resource_names")?
                .extract::<Vec<String>>()?
                .into_iter()
                .collect();
            for function in project.getattr("functions")?.try_iter()? {
                let function = function?;
                let key = function.getattr("key")?;
                if key
                    .getattr("resource_type")?
                    .getattr("value")?
                    .extract::<String>()?
                    == mode
                    && names.contains(&function.getattr("name")?.extract::<String>()?)
                {
                    deps.set_item(key, py.None())?;
                }
            }
        }
    }
    Ok(PyTuple::new(py, deps.keys().iter())?.into_any())
}

pub(super) fn entry<'py>(
    test: &Bound<'py, PyAny>,
    plan: &Bound<'py, PyAny>,
    inputs: (&Bound<'py, PyAny>, &Bound<'py, PyDict>),
    analysis: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = test.py();
    let fields = PyDict::new(py);
    for name in [
        "key",
        "name",
        "source_path",
        "block_index",
        "parent_name",
        "case_name",
        "case_index",
        "case_fingerprint",
        "parameter_schema",
        "parameter_values",
        "scope_deps",
    ] {
        fields.set_item(name, test.getattr(name)?)?;
    }
    for (field, prefix) in [
        ("mock_ref_names", "__ref__"),
        ("mock_source_names", "__source__"),
        ("mock_seed_names", "__seed__"),
        ("mock_dbt_ref_names", "__dbt_ref__"),
        ("mock_table_function_names", "__table_fn__"),
    ] {
        fields.set_item(field, prefixed_names(test, prefix)?)?;
    }
    let mocks = fields
        .get_item("mock_table_function_names")?
        .ok_or_else(|| pyo3::exceptions::PyValueError::new_err("missing mock names"))?;
    fields.set_item(
        "function_deps",
        function_deps(test, plan, inputs.0, (&mocks, inputs.1))?,
    )?;
    fields.set_item("chain", plan.getattr("chain")?)?;
    fields.set_item("assertions", plan.getattr("assertions")?)?;
    fields.set_item("sql_analysis_enabled", analysis)?;
    imported(py, PLAN_MODELS, "SqlTestPlanEntry")?.call((), Some(&fields))
}

pub(super) fn expected_diagnostics(
    test: &Bound<'_, PyAny>,
    plan: &Bound<'_, PyAny>,
    context: &Bound<'_, PyAny>,
) -> PyResult<Vec<String>> {
    let mut result: Vec<String> = Vec::new();
    if context.is_none() {
        return Ok(result);
    }
    let py = test.py();
    let resource_types = imported(py, COMPILE_TYPES, "CompiledResourceType")?;
    for step in plan.getattr("chain")?.try_iter()? {
        let step = step?;
        let name = step.getattr("model_name")?;
        let available = context
            .getattr("authoritative_columns")?
            .call_method1("get", ((resource_types.getattr("MODEL")?, &name),))?;
        let expected = step.getattr("expected_columns")?;
        if expected.is_none() || available.is_none() {
            continue;
        }
        let message = call_with(
            &imported(
                py,
                "sqlbuild.executor.testing.main._missing_expected_columns",
                "describe_missing_expected_columns",
            )?,
            &[
                ("model_name", name.clone()),
                ("expected_columns", expected),
                ("available_columns", available),
            ],
        )?;
        if message.is_none() {
            continue;
        }
        let location = call_with(
            &imported(py, super::constants::FIXTURE_VALIDATION, "fixture_location")?,
            &[
                ("test", test.clone()),
                ("resource_type", resource_types.getattr("SQL_TEST")?),
                ("name", name),
            ],
        )?;
        result.push(format!(
            "SQL test '{}': {}: {}",
            test.getattr("name")?.extract::<String>()?,
            location.extract::<String>()?,
            message.extract::<String>()?
        ));
    }
    Ok(result)
}
