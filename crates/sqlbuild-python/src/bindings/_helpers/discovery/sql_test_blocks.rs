//! SQL `TEST(...)` blocks validated natively and built as discovery records.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};
use sqlbuild_model_config::sql_tests::main::sql_test_block::sql_test_block;
use sqlbuild_model_config::sql_tests::main::sql_test_names_failure::sql_test_names_failure;
use sqlbuild_model_config::sql_tests::models::{SqlTestBlock, SqlTestCase};
use sqlbuild_model_config::sql_values::models::{RawKey, RawSqlValue};

use crate::bindings::_helpers::contracts::sql_values::{SqlValueClasses, raw_value, sql_value};

const MODELS_MODULE: &str = "sqlbuild.compiler.discovery.models";
const ERRORS_MODULE: &str = "sqlbuild.compiler.discovery.exceptions";
const TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";
const SQL_VALUE_TYPES_MODULE: &str = "sqlbuild.sql_values.types";

type NativeBlock<'py> = (Bound<'py, PyDict>, String, Bound<'py, PyAny>);

fn parse_error(py: Python<'_>, message: String) -> PyResult<PyErr> {
    Ok(PyErr::from_value(
        py.import(ERRORS_MODULE)?
            .getattr("SqlTestParseError")?
            .call1((message,))?,
    ))
}

fn header_entries(
    header: &Bound<'_, PyDict>,
    classes: &SqlValueClasses<'_>,
) -> PyResult<Vec<(RawKey, RawSqlValue)>> {
    match raw_value(header.as_any(), classes)? {
        RawSqlValue::Object(entries) => Ok(entries),
        _ => Ok(Vec::new()),
    }
}

fn case_record<'py>(
    py: Python<'py>,
    (case_index, case): (usize, &SqlTestCase),
    classes: &SqlValueClasses<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let mut values: Vec<Bound<'py, PyTuple>> = Vec::with_capacity(case.values.len());
    for (name, value) in &case.values {
        values.push(PyTuple::new(
            py,
            [name.into_bound_py_any(py)?, sql_value(value, classes)?],
        )?);
    }
    py.import(MODELS_MODULE)?
        .getattr("DiscoveredSqlTestCase")?
        .call1((case.name.as_str(), PyTuple::new(py, values)?, case_index))
}

fn block_record<'py>(
    py: Python<'py>,
    (index, native): (usize, &NativeBlock<'py>),
    block: SqlTestBlock,
    classes: &SqlValueClasses<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let models = py.import(MODELS_MODULE)?;
    let kind = py.import(SQL_VALUE_TYPES_MODULE)?.getattr("SqlValueKind")?;
    let parameters = block
        .parameters
        .iter()
        .map(|parameter| {
            models.getattr("SqlTestParameterDeclaration")?.call1((
                parameter.name.as_str(),
                kind.call1((parameter.value_type,))?,
                parameter.nullable,
            ))
        })
        .collect::<PyResult<Vec<_>>>()?;
    let cases = block
        .cases
        .iter()
        .enumerate()
        .map(|(case_index, case)| case_record(py, (case_index, case), classes))
        .collect::<PyResult<Vec<_>>>()?;
    let keywords = PyDict::new(py);
    keywords.set_item("test_index", index)?;
    keywords.set_item("header_values", &native.0)?;
    keywords.set_item("sql_body", native.1.as_str())?;
    keywords.set_item("name", block.name)?;
    keywords.set_item(
        "mode",
        py.import(TYPES_MODULE)?
            .getattr("SqlTestMode")?
            .call1((block.mode,))?,
    )?;
    keywords.set_item("parameters", PyTuple::new(py, parameters)?)?;
    keywords.set_item("cases", PyTuple::new(py, cases)?)?;
    keywords.set_item("cursor_start", block.cursor_start)?;
    keywords.set_item("cursor_end", block.cursor_end)?;
    keywords.set_item("sql_body_span", &native.2)?;
    models
        .getattr("DiscoveredSqlTestBlock")?
        .call((), Some(&keywords))
}

/// Each `(header, sql_body, span)` block of a SQL test file as a `DiscoveredSqlTestBlock`.
#[pyfunction]
fn sql_test_blocks<'py>(
    py: Python<'py>,
    file_path: &str,
    blocks: Vec<NativeBlock<'py>>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let classes = SqlValueClasses::load(py)?;
    let mut records: Vec<Bound<'py, PyAny>> = Vec::with_capacity(blocks.len());
    for (offset, native) in blocks.iter().enumerate() {
        let header = header_entries(&native.0, &classes)?;
        match sql_test_block(&header, &native.1, file_path) {
            Ok(block) => records.push(block_record(py, (offset + 1, native), block, &classes)?),
            Err(message) => return Err(parse_error(py, message)?),
        }
    }
    Ok(records)
}

/// `validate_sql_test_names` over each block's `(test_index, name)`.
#[pyfunction]
fn validate_sql_test_block_names(
    py: Python<'_>,
    file_path: &str,
    blocks: Vec<(usize, Option<String>)>,
) -> Result<(), PyErr> {
    match sql_test_names_failure(file_path, &blocks) {
        None => Ok(()),
        Some(message) => Err(parse_error(py, message)?),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(sql_test_blocks, module)?)?;
    module.add_function(wrap_pyfunction!(validate_sql_test_block_names, module)?)
}
