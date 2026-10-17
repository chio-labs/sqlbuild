//! A discovered SQL model file as a native record whose Python attributes are built on demand.

use std::path::PathBuf;

use crate::bindings::_helpers::records::construct::new_record;
use crate::bindings::_helpers::records::ids::RecordId;
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple};
use pyo3::{FromPyObject, IntoPyObjectExt, pyclass, pymethods};
use sqlbuild_discovery::models::LineColumnSpan;

const FIELD_NAMES: [&str; 10] = [
    "file_path",
    "relative_path",
    "contents",
    "header_values",
    "header_column_locations",
    "output_column_locations",
    "query_sql",
    "enum_declarations",
    "constant_declarations",
    "extract_implicit_alias_columns",
];

/// Authored locations: native rows until Python reads them, then a cached dict.
struct Locations {
    rows: Vec<(String, LineColumnSpan)>,
    projected: PyOnceLock<Py<PyDict>>,
}

impl Locations {
    fn from_rows(rows: Vec<(String, LineColumnSpan)>) -> Self {
        Self {
            rows,
            projected: PyOnceLock::new(),
        }
    }

    /// These locations for another record: the rows, and the dict once Python has read it.
    fn shared(&self, py: Python<'_>) -> Self {
        let projected: PyOnceLock<Py<PyDict>> = PyOnceLock::new();
        if let Some(dict) = self.projected.get(py) {
            let _ = projected.set(py, dict.clone_ref(py));
        }
        Self {
            rows: self.rows.clone(),
            projected,
        }
    }

    fn from_dict(py: Python<'_>, dict: Py<PyDict>) -> Self {
        let projected: PyOnceLock<Py<PyDict>> = PyOnceLock::new();
        let _ = projected.set(py, dict);
        Self {
            rows: Vec::new(),
            projected,
        }
    }

    /// Python's `{name: SourceLocation(...)}`: a repeated name keeps its first position and last value.
    fn dict<'py>(&self, py: Python<'py>, path: &Py<PyAny>) -> PyResult<Bound<'py, PyDict>> {
        Ok(self
            .projected
            .get_or_try_init(py, || {
                let dict: Bound<'py, PyDict> = PyDict::new(py);
                for (name, span) in &self.rows {
                    let location: Bound<'py, PyAny> = new_record(
                        py,
                        RecordId::SourceLocation,
                        (
                            path.bind(py),
                            span.line,
                            span.column,
                            span.end_line,
                            span.end_column,
                        ),
                        None,
                    )?;
                    dict.set_item(name, location)?;
                }
                Ok::<_, pyo3::PyErr>(dict.unbind())
            })?
            .bind(py)
            .clone())
    }
}

/// A discovered SQL model file and its raw contents.
#[pyclass(module = "sqlbuild._native", name = "DiscoveredSqlModelFile", frozen)]
pub(crate) struct NativeModelFile {
    file_path: Py<PyAny>,
    /// `file_path` as a native path, read once so hot paths need not call back into `pathlib`.
    native_file_path: PathBuf,
    relative_path: Py<PyAny>,
    contents: Py<PyString>,
    header_values: Py<PyDict>,
    header_column_locations: Locations,
    output_column_locations: Locations,
    query_sql: Py<PyString>,
    enum_declarations: Py<PyTuple>,
    constant_declarations: Py<PyTuple>,
    extract_implicit_alias_columns: bool,
}

/// What native discovery read for one model file, before its locations are projected.
pub(crate) struct ModelFileParts {
    pub(crate) file_path: Py<PyAny>,
    pub(crate) relative_path: Py<PyAny>,
    pub(crate) contents: Py<PyString>,
    pub(crate) header_values: Py<PyDict>,
    pub(crate) header_column_locations: Vec<(String, LineColumnSpan)>,
    pub(crate) output_column_locations: Vec<(String, LineColumnSpan)>,
    pub(crate) query_sql: Py<PyString>,
    pub(crate) declarations: (Py<PyTuple>, Py<PyTuple>),
    pub(crate) extract_implicit_alias_columns: bool,
}

/// The keyword fields Python constructs a model file record with.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct ModelFileFields {
    file_path: Py<PyAny>,
    relative_path: Py<PyAny>,
    contents: Py<PyString>,
    header_values: Py<PyDict>,
    header_column_locations: Py<PyDict>,
    output_column_locations: Py<PyDict>,
    query_sql: Py<PyString>,
    #[pyo3(default)]
    enum_declarations: Option<Py<PyTuple>>,
    #[pyo3(default)]
    constant_declarations: Option<Py<PyTuple>>,
    #[pyo3(default = true)]
    extract_implicit_alias_columns: bool,
}

impl NativeModelFile {
    pub(crate) fn discovered(py: Python<'_>, parts: ModelFileParts) -> PyResult<Self> {
        let (enum_declarations, constant_declarations) = parts.declarations;
        Ok(Self {
            native_file_path: parts.file_path.bind(py).extract()?,
            file_path: parts.file_path,
            relative_path: parts.relative_path,
            contents: parts.contents,
            header_values: parts.header_values,
            header_column_locations: Locations::from_rows(parts.header_column_locations),
            output_column_locations: Locations::from_rows(parts.output_column_locations),
            query_sql: parts.query_sql,
            enum_declarations,
            constant_declarations,
            extract_implicit_alias_columns: parts.extract_implicit_alias_columns,
        })
    }

    pub(crate) fn header_locations<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        self.header_column_locations.dict(py, &self.relative_path)
    }

    pub(crate) fn header_value_dict<'py>(&self, py: Python<'py>) -> &Bound<'py, PyDict> {
        self.header_values.bind(py)
    }

    pub(crate) fn declaration_tuples<'py>(
        &self,
        py: Python<'py>,
    ) -> (&Bound<'py, PyTuple>, &Bound<'py, PyTuple>) {
        (
            self.enum_declarations.bind(py),
            self.constant_declarations.bind(py),
        )
    }

    /// The file path as a native path.
    pub(crate) fn file_path_buf(&self) -> PathBuf {
        self.native_file_path.clone()
    }

    pub(crate) fn paths<'py>(&self, py: Python<'py>) -> (&Bound<'py, PyAny>, &Bound<'py, PyAny>) {
        (self.file_path.bind(py), self.relative_path.bind(py))
    }

    pub(crate) fn texts<'py>(
        &self,
        py: Python<'py>,
    ) -> (&Bound<'py, PyString>, &Bound<'py, PyString>) {
        (self.query_sql.bind(py), self.contents.bind(py))
    }

    fn fields<'py>(&self, py: Python<'py>) -> PyResult<Vec<Bound<'py, PyAny>>> {
        Ok(vec![
            self.file_path.bind(py).clone(),
            self.relative_path.bind(py).clone(),
            self.contents.bind(py).clone().into_any(),
            self.header_values.bind(py).clone().into_any(),
            self.header_locations(py)?.into_any(),
            self.output_column_locations
                .dict(py, &self.relative_path)?
                .into_any(),
            self.query_sql.bind(py).clone().into_any(),
            self.enum_declarations.bind(py).clone().into_any(),
            self.constant_declarations.bind(py).clone().into_any(),
            pyo3::types::PyBool::new(py, self.extract_implicit_alias_columns)
                .to_owned()
                .into_any(),
        ])
    }
}

#[pymethods]
impl NativeModelFile {
    #[new]
    #[pyo3(signature = (**fields))]
    fn new(py: Python<'_>, fields: Option<Bound<'_, PyDict>>) -> PyResult<Self> {
        let Some(fields) = fields else {
            return Err(PyTypeError::new_err(
                "DiscoveredSqlModelFile requires its fields",
            ));
        };
        for key in fields.keys() {
            let key: String = key.extract()?;
            if !FIELD_NAMES.contains(&key.as_str()) {
                return Err(PyTypeError::new_err(format!(
                    "DiscoveredSqlModelFile got an unexpected keyword argument '{key}'"
                )));
            }
        }
        let fields: ModelFileFields = fields.extract()?;
        Ok(Self {
            native_file_path: fields.file_path.bind(py).extract()?,
            file_path: fields.file_path,
            relative_path: fields.relative_path,
            contents: fields.contents,
            header_values: fields.header_values,
            header_column_locations: Locations::from_dict(py, fields.header_column_locations),
            output_column_locations: Locations::from_dict(py, fields.output_column_locations),
            query_sql: fields.query_sql,
            enum_declarations: fields
                .enum_declarations
                .unwrap_or_else(|| PyTuple::empty(py).unbind()),
            constant_declarations: fields
                .constant_declarations
                .unwrap_or_else(|| PyTuple::empty(py).unbind()),
            extract_implicit_alias_columns: fields.extract_implicit_alias_columns,
        })
    }

    /// This file with edited contents and query, as `dataclasses.replace` would make it.
    pub(crate) fn with_text(
        &self,
        py: Python<'_>,
        contents: Py<PyString>,
        query_sql: Py<PyString>,
    ) -> Self {
        Self {
            native_file_path: self.native_file_path.clone(),
            file_path: self.file_path.clone_ref(py),
            relative_path: self.relative_path.clone_ref(py),
            contents,
            header_values: self.header_values.clone_ref(py),
            header_column_locations: self.header_column_locations.shared(py),
            output_column_locations: self.output_column_locations.shared(py),
            query_sql,
            enum_declarations: self.enum_declarations.clone_ref(py),
            constant_declarations: self.constant_declarations.clone_ref(py),
            extract_implicit_alias_columns: self.extract_implicit_alias_columns,
        }
    }

    #[getter]
    pub(crate) fn file_path(&self, py: Python<'_>) -> Py<PyAny> {
        self.file_path.clone_ref(py)
    }

    #[getter]
    pub(crate) fn relative_path(&self, py: Python<'_>) -> Py<PyAny> {
        self.relative_path.clone_ref(py)
    }

    #[getter]
    pub(crate) fn contents(&self, py: Python<'_>) -> Py<PyString> {
        self.contents.clone_ref(py)
    }

    #[getter]
    pub(crate) fn header_values(&self, py: Python<'_>) -> Py<PyDict> {
        self.header_values.clone_ref(py)
    }

    #[getter]
    pub(crate) fn header_column_locations<'py>(
        &self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyDict>> {
        self.header_locations(py)
    }

    #[getter]
    pub(crate) fn output_column_locations<'py>(
        &self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyDict>> {
        self.output_column_locations.dict(py, &self.relative_path)
    }

    #[getter]
    pub(crate) fn query_sql(&self, py: Python<'_>) -> Py<PyString> {
        self.query_sql.clone_ref(py)
    }

    #[getter]
    pub(crate) fn enum_declarations(&self, py: Python<'_>) -> Py<PyTuple> {
        self.enum_declarations.clone_ref(py)
    }

    #[getter]
    pub(crate) fn constant_declarations(&self, py: Python<'_>) -> Py<PyTuple> {
        self.constant_declarations.clone_ref(py)
    }

    #[getter]
    pub(crate) fn extract_implicit_alias_columns(&self) -> bool {
        self.extract_implicit_alias_columns
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let Ok(other) = other.downcast::<NativeModelFile>() else {
            return Ok(py.NotImplemented());
        };
        let other: &NativeModelFile = other.get();
        for (left, right) in self.fields(py)?.iter().zip(other.fields(py)?) {
            if !left.eq(right)? {
                return false.into_py_any(py);
            }
        }
        true.into_py_any(py)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let fields: Vec<String> = FIELD_NAMES
            .iter()
            .zip(self.fields(py)?)
            .map(|(name, value)| Ok(format!("{name}={}", value.repr()?)))
            .collect::<PyResult<_>>()?;
        Ok(format!("DiscoveredSqlModelFile({})", fields.join(", ")))
    }

    /// The keyword fields `copy` and `pickle` rebuild this record from.
    fn __getnewargs_ex__<'py>(
        slf: &Bound<'py, Self>,
    ) -> PyResult<(Bound<'py, PyTuple>, Bound<'py, PyDict>)> {
        let py: Python<'py> = slf.py();
        let keywords: Bound<'py, PyDict> = PyDict::new(py);
        for (name, value) in FIELD_NAMES.iter().zip(slf.get().fields(py)?) {
            keywords.set_item(name, value)?;
        }
        Ok((PyTuple::empty(py), keywords))
    }
}
