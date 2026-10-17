//! Fixture schema conversion at the Python model boundary.

use pyo3::exceptions::{PyOSError, PySyntaxError, PyUnicodeError, PyValueError};
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyStringMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_rules::lint_text::main::format_fixture_blocks::format_fixture_blocks;
use sqlbuild_rules::lint_text::main::simplify_fixture_nulls::simplify_fixture_nulls;
use sqlbuild_rules::lint_text::models::FixtureFormatBlock;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::bindings::_helpers::boundary::panics::{compiler_guard, value_error};
use crate::bindings::_helpers::discovery::sql_test_records::parse_sql_test_file;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::rules::constants::MODEL_TEST_MODE;
use crate::bindings::_helpers::rules::fixture_schemas;
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;

#[pyfunction]
#[pyo3(signature = (*, sql, relation))]
fn simplify_fixture_null_projections(sql: &str, relation: &Bound<'_, PyAny>) -> PyResult<String> {
    let columns = fixture_schemas::columns(&native_field(relation, "columns")?)?;
    compiler_guard(|| simplify_fixture_nulls(sql, &columns).map_err(value_error))
}

#[pyfunction]
#[pyo3(signature = (*, files, project_dir, discovered_inputs, sql_lexical_syntax))]
pub(crate) fn format_redundant_fixture_nulls<'py>(
    files: &Bound<'py, PyDict>,
    project_dir: &Bound<'py, PyAny>,
    discovered_inputs: &Bound<'py, PyAny>,
    sql_lexical_syntax: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    compiler_guard(|| {
        let py = files.py();
        let relations = fixture_schemas::relations(discovered_inputs)?;
        let syntax: LexicalSyntax = native_field(sql_lexical_syntax, "native_mapping")?
            .extract::<LexicalSyntaxInput>()?
            .into();
        let updated = PyDict::new(py);
        for file in native_field(discovered_inputs, "test_files")?.try_iter()? {
            let file = file?;
            let relative = native_field(&file, "relative_path")?;
            let path = project_dir
                .call_method1("__truediv__", (&relative,))?
                .call_method0("resolve")?;
            let Some(original) = files.get_item(&path)? else {
                continue;
            };
            let contents: String = updated.get_item(&path)?.unwrap_or(original).extract()?;
            let blocks = match parse_sql_test_file(contents.clone(), &path) {
                Ok(blocks) => blocks,
                Err(error)
                    if error.is_instance_of::<PyOSError>(py)
                        || error.is_instance_of::<PyUnicodeError>(py)
                        || error.is_instance_of::<PyValueError>(py)
                        || error.is_instance_of::<PySyntaxError>(py) =>
                {
                    continue;
                }
                Err(error) => return Err(error),
            };
            let blocks = blocks
                .try_iter()?
                .map(|block| {
                    let block = block?;
                    Ok(FixtureFormatBlock {
                        sql_body: native_field(&block, "sql_body")?.extract()?,
                        model_mode: native_field(&native_field(&block, "mode")?, "value")?
                            .extract::<String>()?
                            == MODEL_TEST_MODE,
                    })
                })
                .collect::<PyResult<Vec<_>>>()?;
            let label = relative.str()?.to_str()?.to_owned();
            if let Some(result) =
                format_fixture_blocks((&contents, &label), &blocks, &relations, &syntax)
                    .map_err(value_error)?
            {
                updated.set_item(path, result)?;
            }
        }
        Ok(updated)
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(simplify_fixture_null_projections, module)?)?;
    module.add_function(wrap_pyfunction!(format_redundant_fixture_nulls, module)?)
}
