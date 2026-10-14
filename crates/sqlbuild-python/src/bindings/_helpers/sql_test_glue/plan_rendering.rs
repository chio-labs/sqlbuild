//! Adapter rendering and declared cursor-window boundaries for native test planning.

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::sql_test_glue::plan_values::{model_payload, string};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};

use crate::bindings::_helpers::sql_test_glue::constants::{CURSOR_WINDOW, SENTINEL};

pub(super) fn mentions(sql: &str) -> bool {
    ["__cursor_start", "__cursor_end"]
        .iter()
        .any(|name| sql.contains(name))
}

fn render<'py>(
    sql: Bound<'py, PyAny>,
    model: Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
    test: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    call_with(
        &imported(adapter.py(), CURSOR_WINDOW, "render_test_cursor_intrinsics")?,
        &[
            ("sql", sql),
            ("model", model),
            ("adapter", adapter.clone()),
            ("test", test),
        ],
    )
}

pub(super) fn models<'py>(
    project: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py = project.py();
    let result = PyDict::new(py);
    for (index, model) in project.getattr("models")?.try_iter()?.enumerate() {
        let model = model?;
        let sql = model.getattr("query_sql")?;
        if mentions(&sql.extract::<String>()?) {
            result.set_item(
                index,
                render(sql, model, adapter, py.None().into_bound(py))?,
            )?;
        }
    }
    Ok(result)
}

pub(super) fn overrides<'py>(
    project: &Bound<'py, PyAny>,
    tests: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py = project.py();
    let models = PyDict::new(py);
    for model in project.getattr("models")?.try_iter()? {
        let model = model?;
        models.set_item(model.getattr("name")?, model)?;
    }
    let tests: Vec<Bound<'py, PyAny>> = tests.extract()?;
    let mut indexes: Vec<usize> = Vec::new();
    let mut windowed: Vec<Bound<'py, PyAny>> = Vec::new();
    for (index, test) in tests.iter().enumerate() {
        if model_payload(test)?
            && call_with(
                &imported(py, CURSOR_WINDOW, "declares_cursor_window")?,
                &[("test", test.clone())],
            )?
            .is_truthy()?
        {
            indexes.push(index);
            windowed.push(test.clone());
        }
    }
    let chains = if indexes.is_empty() {
        Vec::new()
    } else {
        super::plan_driver::chains(project, &PyTuple::new(py, windowed)?.into_any())?
            .extract::<Vec<Bound<'py, PyAny>>>()?
    };
    if indexes.len() != chains.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "zip() argument lengths differ",
        ));
    }
    let chains: std::collections::BTreeMap<_, _> = indexes.into_iter().zip(chains).collect();
    let result = PyDict::new(py);
    for (index, test) in tests.iter().enumerate() {
        if !model_payload(test)? {
            continue;
        }
        let overrides = test
            .getattr("payload")?
            .getattr("model_query_overrides")?
            .cast_into::<PyDict>()?;
        let chain = chains.get(&index);
        if chain.is_none()
            && !overrides
                .values()
                .try_iter()?
                .map(|value| Ok(mentions(&value?.extract::<String>()?)))
                .collect::<PyResult<Vec<bool>>>()?
                .contains(&true)
        {
            continue;
        }
        let chain_names: Vec<String> = chain
            .map(|value| value.extract())
            .transpose()?
            .unwrap_or_default();
        let rendered = PyDict::new(py);
        for (name, sql) in overrides.iter() {
            let name: String = name.extract()?;
            let sql = if let Some(model) = models.get_item(&name)? {
                render(
                    sql,
                    model,
                    adapter,
                    if chain_names.contains(&name) {
                        test.clone()
                    } else {
                        py.None().into_bound(py)
                    },
                )?
            } else {
                sql
            };
            rendered.set_item(name, sql)?;
        }
        if chain.is_some() {
            let mut chain_models: Vec<Bound<'py, PyAny>> = Vec::new();
            for name in chain_names {
                if let Some(model) = models.get_item(name)? {
                    chain_models.push(model);
                }
            }
            let cursor_models = call_with(
                &imported(py, CURSOR_WINDOW, "declared_window_cursor_models")?,
                &[
                    ("test", test.clone()),
                    ("chain_models", PyTuple::new(py, chain_models)?.into_any()),
                ],
            )?;
            for model in cursor_models.try_iter()? {
                let model = model?;
                let name = model.getattr("name")?;
                if !rendered.contains(&name)? {
                    rendered.set_item(
                        name,
                        render(model.getattr("query_sql")?, model, adapter, test.clone())?,
                    )?;
                }
            }
        }
        result.set_item(index, rendered)?;
    }
    Ok(result)
}

pub(super) fn functions<'py>(
    project: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py = project.py();
    let mut result: Vec<Bound<'py, PyTuple>> = Vec::new();
    for function in project.getattr("functions")?.try_iter()? {
        let function = function?;
        let target = function.getattr("destination")?.getattr("qualified_name")?;
        if target.is_none() {
            continue;
        }
        let mut fields = vec![function.getattr("name")?];
        for method in ["render_udf_call", "render_table_function_call"] {
            let rendered: String = call_with(
                &adapter.getattr(method)?,
                &[
                    ("target", target.clone()),
                    ("call_suffix_sql", string(py, SENTINEL)),
                ],
            )?
            .extract()?;
            let Some((prefix, suffix)) = rendered
                .split_once(SENTINEL)
                .filter(|(_, suffix)| !suffix.contains(SENTINEL))
            else {
                return Err(PyErr::from_value(
                    imported(
                        py,
                        "sqlbuild.compiler.planner.exceptions",
                        "NativeSqlTestPlanningError",
                    )?
                    .call1(("adapter SQL function call template is not deterministic",))?,
                ));
            };
            fields.push(string(py, prefix));
            fields.push(string(py, suffix));
        }
        result.push(PyTuple::new(py, fields)?);
    }
    PyTuple::new(py, result)
}
