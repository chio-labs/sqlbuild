//! Complete SQL-test fixtures through the existing fixture completion boundary.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::sql_test_glue::authored_ctes::prefixed_ctes;
use crate::bindings::_helpers::sql_test_glue::constants::{FIXTURE_VALIDATION, NATIVE_PLANNING};
use crate::bindings::_helpers::sql_test_glue::plan_values::model_payload;

pub(super) fn validated_test<'py>(
    test: &Bound<'py, PyAny>,
    chain: &Bound<'py, PyAny>,
    inputs: (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    context: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = test.py();
    let payload = test.getattr("payload")?;
    let ctes = payload.getattr("authored_ctes")?;
    let expected = payload.getattr("expected_ctes")?;
    let completed = call_with(
        &imported(py, FIXTURE_VALIDATION, "build_validated_test_fixtures")?,
        &[
            ("test", test.clone()),
            ("project", inputs.0.clone()),
            ("adapter", inputs.1.clone()),
            ("ordered_model_names", chain.clone()),
            ("mock_refs", prefixed_ctes(&ctes, "__ref__")?.into_any()),
            (
                "mock_sources",
                prefixed_ctes(&ctes, "__source__")?.into_any(),
            ),
            ("mock_seeds", prefixed_ctes(&ctes, "__seed__")?.into_any()),
            (
                "expected_outputs",
                prefixed_ctes(&expected, "__expected__")?.into_any(),
            ),
            ("planning_context", context.clone()),
        ],
    )?;
    let replace = imported(py, "dataclasses", "replace")?;
    let mut authored: Vec<Bound<'py, PyAny>> = Vec::new();
    for cte in ctes.try_iter()? {
        let cte = cte?;
        let name: String = cte.getattr("name")?.extract()?;
        let mut replacement = cte.clone();
        for (index, prefix) in ["__ref__", "__source__", "__seed__"].iter().enumerate() {
            if let Some(name) = name.strip_prefix(prefix) {
                let sql = completed
                    .get_item(index)?
                    .call_method1("get", (name, cte.getattr("sql_body")?))?;
                let kwargs = PyDict::new(py);
                kwargs.set_item("sql_body", sql)?;
                replacement = replace.call((&cte,), Some(&kwargs))?;
                break;
            }
        }
        authored.push(replacement);
    }
    let mut expected_ctes: Vec<Bound<'py, PyAny>> = Vec::new();
    for cte in expected.try_iter()? {
        let cte = cte?;
        let name: String = cte.getattr("name")?.extract()?;
        let name = name.strip_prefix("__expected__").unwrap_or(&name);
        let kwargs = PyDict::new(py);
        kwargs.set_item(
            "sql_body",
            completed
                .get_item(3)?
                .call_method1("get", (name, cte.getattr("sql_body")?))?,
        )?;
        expected_ctes.push(replace.call((&cte,), Some(&kwargs))?);
    }
    let kwargs = PyDict::new(py);
    kwargs.set_item("authored_ctes", PyTuple::new(py, authored)?)?;
    kwargs.set_item("expected_ctes", PyTuple::new(py, expected_ctes)?)?;
    let payload = replace.call((payload,), Some(&kwargs))?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("payload", payload)?;
    replace.call((test,), Some(&kwargs))
}

pub(super) fn validate<'py>(
    tests: &[Bound<'py, PyAny>],
    inputs: (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    context: &Bound<'py, PyAny>,
) -> PyResult<super::types::ValidatedTests<'py>> {
    let py = context.py();
    let mut model_tests: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut indexes: Vec<usize> = Vec::new();
    for (index, test) in tests.iter().enumerate() {
        if model_payload(test)? {
            indexes.push(index);
            model_tests.push(test.clone());
        }
    }
    if indexes.is_empty() {
        return Ok((tests.to_vec(), Default::default()));
    }
    let chains = call_with(
        &imported(py, NATIVE_PLANNING, "resolve_sql_test_model_chains")?,
        &[
            ("project", inputs.0.clone()),
            ("tests", PyTuple::new(py, model_tests)?.into_any()),
        ],
    )?;
    let chains: Vec<Bound<'py, PyAny>> = chains.extract()?;
    if chains.len() != indexes.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "zip() argument lengths differ",
        ));
    }
    let exception = imported(
        py,
        "sqlbuild.compiler.planner.exceptions",
        "SqlTestFixtureValidationError",
    )?;
    let mut validated = tests.to_vec();
    let mut diagnostics: std::collections::BTreeMap<usize, Bound<'py, PyAny>> =
        std::collections::BTreeMap::new();
    for (index, chain) in indexes.into_iter().zip(chains) {
        match validated_test(&tests[index], &chain, inputs, context) {
            Ok(test) => validated[index] = test,
            Err(error) if error.value(py).is_instance(&exception)? => {
                diagnostics.insert(index, error.value(py).getattr("diagnostics")?);
            }
            Err(error) => return Err(error),
        }
    }
    Ok((validated, diagnostics))
}
