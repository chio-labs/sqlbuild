//! A compiled model's authored cursor inputs resolved into filter and watermark roles.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::{PyDict, PyDictMethods, PyList, PyListMethods, PyString};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const CURSOR_INPUTS_KEY: &str = "cursor_inputs";
const FILTER_ROLE: &str = "filter";
const WATERMARK_ROLE: &str = "watermark";
const WATERMARK_STRATEGY: &str = "watermark";
const ROLLING_WINDOW_STRATEGY: &str = "rolling_window";

/// Watermark-strategy cursor inputs: each relation's column under the roles it declares.
fn role_blocks<'py>(
    authored: &Bound<'py, PyDict>,
    (filter, watermark): (&Bound<'py, PyDict>, &Bound<'py, PyDict>),
) -> PyResult<()> {
    for (relation, block) in authored.iter() {
        let (true, Ok(block)) = (
            relation.is_instance_of::<PyString>(),
            block.downcast::<PyDict>(),
        ) else {
            continue;
        };
        let column: Option<Bound<'py, PyAny>> = block.get_item("column")?;
        let roles: Option<Bound<'py, PyAny>> = block.get_item("roles")?;
        let (Some(column), Some(roles)) = (column, roles) else {
            continue;
        };
        let (true, Ok(roles)) = (
            column.is_instance_of::<PyString>(),
            roles.downcast::<PyList>(),
        ) else {
            continue;
        };
        if roles.contains(FILTER_ROLE)? {
            filter.set_item(&relation, &column)?;
        }
        if roles.contains(WATERMARK_ROLE)? {
            watermark.set_item(&relation, &column)?;
        }
    }
    Ok(())
}

/// The string-to-string entries of an authored mapping.
fn string_map<'py>(authored: &Bound<'py, PyDict>) -> PyResult<Bound<'py, PyDict>> {
    let result: Bound<'py, PyDict> = PyDict::new(authored.py());
    for (key, item) in authored.iter() {
        if key.is_instance_of::<PyString>() && item.is_instance_of::<PyString>() {
            result.set_item(key, item)?;
        }
    }
    Ok(result)
}

/// Resolve authored cursor input fields into explicit effective roles.
#[pyfunction]
#[pyo3(signature = (*, model))]
pub(crate) fn resolve_cursor_input_roles<'py>(
    model: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = model.py();
    let values: Bound<'py, PyAny> = model.getattr("config")?.getattr("values")?;
    let authored: Bound<'py, PyAny> = values.call_method1("get", (CURSOR_INPUTS_KEY,))?;
    let strategy: Bound<'py, PyAny> = values.call_method1("get", ("microbatch_strategy",))?;
    let rolling: bool = strategy.eq(ROLLING_WINDOW_STRATEGY)?;
    let mut filter: Bound<'py, PyDict> = PyDict::new(py);
    let mut watermark: Bound<'py, PyDict> = PyDict::new(py);
    match authored.downcast::<PyDict>() {
        Ok(authored) if strategy.eq(WATERMARK_STRATEGY)? => {
            role_blocks(authored, (&filter, &watermark))?;
        }
        Ok(authored) => {
            filter = string_map(authored)?;
            if !rolling {
                watermark = filter.clone();
            }
        }
        Err(_) => {
            let cursor: Bound<'py, PyAny> = values.call_method1("get", ("cursor",))?;
            if cursor.is_instance_of::<PyString>() {
                for reference in model.getattr("references")?.try_iter()? {
                    filter.set_item(reference?.getattr("ref_name")?, &cursor)?;
                }
            }
            if !rolling {
                watermark = filter.clone();
            }
        }
    }
    call_with(
        &imported(py, COMPILE_MODELS_MODULE, "CursorInputRoles")?,
        &[
            ("filter_inputs", filter.into_any()),
            ("watermark_inputs", watermark.into_any()),
        ],
    )
}
