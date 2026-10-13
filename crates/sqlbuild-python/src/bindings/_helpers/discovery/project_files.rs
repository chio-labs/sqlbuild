//! Native discovery results as the plain data the Python discovery facade materialises.

use pyo3::exceptions::PyException;
use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyString};
use pyo3::{IntoPyObjectExt, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_discovery::model_files::main::parse_model_text::parse_model_text;
use sqlbuild_discovery::model_files::models::{DiscoveredModelFile, ModelFileOptions};
use sqlbuild_discovery::tree::models::ProjectTree;
use std::path::Path;

use crate::bindings::_helpers::discovery::declaration_records::source_locations;
use crate::bindings::_helpers::discovery::header_declarations::{
    HeaderDeclarations, model_header_declarations,
};
use crate::bindings::_helpers::discovery::model_file_record::{ModelFileParts, NativeModelFile};
use crate::bindings::_helpers::discovery::raised::failure_error;
use crate::bindings::_helpers::sqltext::authored_values::map_to_python;
use crate::bindings::models::{ModelTextRequest, NativeProjectTree};
use crate::bindings::types::CompilerDetach;

pub(crate) type PyObject = Py<PyAny>;

const STEM_ATTRIBUTE: &str = "stem";
const ENUMS_KEY: &str = "enums";
const CONSTANTS_KEY: &str = "constants";

/// A relative path as Python names it: the real, surrogate-escaped name where it is not UTF-8.
pub(crate) fn path_object(
    py: Python<'_>,
    tree: &ProjectTree,
    relative_path: String,
) -> PyResult<PyObject> {
    match tree.raw_relative(&relative_path) {
        Some(raw) => raw.into_os_string().into_py_any(py),
        None => relative_path.into_py_any(py),
    }
}

#[pymethods]
impl NativeProjectTree {
    #[new]
    fn new(project_dir: &str) -> Self {
        Self {
            inner: ProjectTree::new(Path::new(project_dir)),
        }
    }
}

/// One parsed model file's record, or its header declaration error, raised only if it is built.
pub(crate) fn model_record<'py>(
    py: Python<'py>,
    model: DiscoveredModelFile,
    paths: (Bound<'py, PyAny>, Bound<'py, PyAny>),
    extract_implicit_alias_columns: bool,
) -> PyResult<Result<PyObject, PyErr>> {
    let (file_path, relative_path) = paths;
    let header_values: Bound<'py, PyDict> = map_to_python(py, model.header_values)?
        .into_bound(py)
        .downcast_into::<PyDict>()?;
    let model_name: String = file_path.getattr(STEM_ATTRIBUTE)?.extract()?;
    let declarations: HeaderDeclarations<'py> = match model_header_declarations(
        py,
        (
            header_values.get_item(ENUMS_KEY)?,
            header_values.get_item(CONSTANTS_KEY)?,
        ),
        model_name,
        relative_path.clone(),
    ) {
        Ok(declarations) => declarations,
        Err(error) if error.is_instance_of::<PyException>(py) => return Ok(Err(error)),
        Err(error) => return Err(error),
    };
    let (enum_declarations, constant_declarations) = declarations;
    let record: NativeModelFile = NativeModelFile::discovered(ModelFileParts {
        file_path: file_path.unbind(),
        relative_path: relative_path.unbind(),
        contents: PyString::new(py, &model.contents).unbind(),
        header_values: header_values.unbind(),
        header_column_locations: model.header_column_locations,
        output_column_locations: model.output_column_locations,
        query_sql: PyString::new(py, &model.query_sql).unbind(),
        declarations: (enum_declarations.unbind(), constant_declarations.unbind()),
        extract_implicit_alias_columns,
    });
    Ok(Ok(record.into_py_any(py)?))
}

/// Parse model contents as discovery does: `(header_values, query_sql, column locations)`.
#[pyfunction]
fn parse_model_contents(
    py: Python<'_>,
    request: ModelTextRequest,
    contents: String,
) -> PyResult<(PyObject, String, PyObject)> {
    let options = ModelFileOptions {
        supported_keys: request.supported_keys,
        removed_keys: request.removed_keys,
        extract_implicit_alias_columns: request.extract_implicit_alias_columns,
        extract_output_column_locations: request.extract_output_column_locations,
    };
    let parsed = py
        .compiler_detach(|| Ok(parse_model_text(&request.file_path, contents, &options)))
        .map_err(crate::bindings::_helpers::boundary::panics::compiler_error)?;
    let model: DiscoveredModelFile = parsed.map_err(|failure| failure_error(py, failure))?;
    let path: Bound<'_, PyAny> = py
        .import("pathlib")?
        .getattr("Path")?
        .call1((request.file_path.as_str(),))?;
    Ok((
        map_to_python(py, model.header_values)?,
        model.query_sql,
        source_locations(py, &path, &model.header_column_locations)?
            .into_any()
            .unbind(),
    ))
}

/// Whether native discovery reproduces the string semantics of this Python and Unicode version.
pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeProjectTree>()?;
    module.add_class::<NativeModelFile>()?;
    module.add_function(wrap_pyfunction!(parse_model_contents, module)?)?;
    Ok(())
}
