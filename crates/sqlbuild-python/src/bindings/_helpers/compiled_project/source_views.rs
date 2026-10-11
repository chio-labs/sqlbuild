//! Sources attached by the native loop, held by the compiled project, and their views.

use pyo3::exceptions::PyIndexError;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{pyclass, pymethods};

use crate::bindings::_helpers::compiled_project::compiled_model_view::object_key;
use crate::bindings::_helpers::compiled_project::model_input_view::{
    InputViewClasses, view_classes,
};
use crate::bindings::_helpers::compiled_project::project::NativeCompiledProject;

const SOURCE_RESOURCE: &str = "source";
const DATACLASSES_MODULE: &str = "dataclasses";
const REPLACE_FUNCTION: &str = "replace";

/// `(database, schema)` native project assembly resolved for a source, or `None`.
pub(crate) type SourceNamespace = Option<(Option<String>, Option<String>)>;

/// What the source loop attached for one source: its expanded metadata and usages.
pub(crate) struct AttachedSource {
    /// The discovered source file.
    pub(crate) source_file: Py<PyAny>,
    /// The discovered entry; its spec carries user-authored metadata.
    pub(crate) entry: Py<PyAny>,
    pub(crate) name: String,
    pub(crate) contract: Option<String>,
    pub(crate) database: Option<String>,
    pub(crate) schema: Option<String>,
    pub(crate) table: Option<String>,
    pub(crate) expression: Option<String>,
    pub(crate) description: Option<String>,
    /// Template-expanded user metadata.
    pub(crate) meta: Py<PyAny>,
    /// Template-expanded column specs, which carry user metadata and audit arguments.
    pub(crate) columns: Py<PyTuple>,
    /// Template-expanded table audit specs, which carry user audit arguments.
    pub(crate) audits: Py<PyTuple>,
    /// Usage records, the identities the scope index is built from.
    pub(crate) usages: Py<PyTuple>,
}

/// One attached source held by the compiled project.
pub(crate) struct SourceRecord {
    attached: AttachedSource,
    /// The namespace native project assembly resolved, once it ran.
    namespace: Option<SourceNamespace>,
    attached_entry: PyOnceLock<Py<PyAny>>,
    assembled_entry: PyOnceLock<Py<PyAny>>,
    key: PyOnceLock<Py<PyAny>>,
}

impl SourceRecord {
    pub(crate) fn new(attached: AttachedSource) -> Self {
        Self {
            attached,
            namespace: None,
            attached_entry: PyOnceLock::new(),
            assembled_entry: PyOnceLock::new(),
            key: PyOnceLock::new(),
        }
    }

    /// The attached source.
    pub(crate) fn attached(&self) -> &AttachedSource {
        &self.attached
    }

    /// Keep the namespace native project assembly resolved for the source.
    pub(crate) fn set_namespace(&mut self, namespace: SourceNamespace) {
        self.namespace = Some(namespace);
    }

    /// The attached `SourceEntry`: the discovered entry with its expanded metadata.
    fn attached_entry(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.attached_entry
            .get_or_try_init(py, || {
                let source: &AttachedSource = &self.attached;
                let changes: Bound<'_, PyDict> = PyDict::new(py);
                changes.set_item("contract", &source.contract)?;
                changes.set_item("database", &source.database)?;
                changes.set_item("schema", &source.schema)?;
                changes.set_item("table", &source.table)?;
                changes.set_item("expression", &source.expression)?;
                changes.set_item("description", &source.description)?;
                changes.set_item("meta", source.meta.bind(py))?;
                changes.set_item("columns", source.columns.bind(py))?;
                changes.set_item("audits", source.audits.bind(py))?;
                replaced(py, source.entry.bind(py), &changes)
            })
            .map(|entry| entry.clone_ref(py))
    }

    /// The assembled `SourceEntry`: the attached entry in its resolved namespace.
    fn assembled_entry(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let attached: Py<PyAny> = self.attached_entry(py)?;
        let Some(Some((database, schema))) = &self.namespace else {
            return Ok(attached);
        };
        self.assembled_entry
            .get_or_try_init(py, || {
                let changes: Bound<'_, PyDict> = PyDict::new(py);
                changes.set_item("database", database)?;
                changes.set_item("schema", schema)?;
                replaced(py, attached.bind(py), &changes)
            })
            .map(|entry| entry.clone_ref(py))
    }
}

/// `dataclasses.replace(value, **changes)`.
pub(crate) fn replaced(
    py: Python<'_>,
    value: &Bound<'_, PyAny>,
    changes: &Bound<'_, PyDict>,
) -> PyResult<Py<PyAny>> {
    Ok(py
        .import(DATACLASSES_MODULE)?
        .getattr(REPLACE_FUNCTION)?
        .call((value,), Some(changes))?
        .unbind())
}

fn read_source<'py, T>(
    owner: &Py<NativeCompiledProject>,
    index: usize,
    py: Python<'py>,
    read: impl FnOnce(&SourceRecord, Python<'py>) -> PyResult<T>,
) -> PyResult<T> {
    let owner = owner.bind(py).borrow();
    let source: &SourceRecord = owner
        .sources()
        .get(index)
        .ok_or_else(|| PyIndexError::new_err(index))?;
    read(source, py)
}

/// One attached source, read from the compiled project that owns it.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeSourceInput {
    owner: Py<NativeCompiledProject>,
    index: usize,
}

impl NativeSourceInput {
    pub(crate) fn new(owner: Py<NativeCompiledProject>, index: usize) -> Self {
        Self { owner, index }
    }
}

#[pymethods]
impl NativeSourceInput {
    #[getter]
    fn source_entry(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        read_source(&self.owner, self.index, py, |source, py| {
            source.attached_entry(py)
        })
    }

    #[getter]
    fn source_file(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        read_source(&self.owner, self.index, py, |source, py| {
            Ok(source.attached.source_file.clone_ref(py))
        })
    }

    #[getter]
    fn declaration_usages(&self, py: Python<'_>) -> PyResult<Py<PyTuple>> {
        read_source(&self.owner, self.index, py, |source, py| {
            Ok(source.attached.usages.clone_ref(py))
        })
    }

    /// `(name, has a loader, database, schema)`, what project assembly resolves a namespace from.
    #[getter]
    fn assembly_row(
        &self,
        py: Python<'_>,
    ) -> PyResult<(String, bool, Option<String>, Option<String>)> {
        read_source(&self.owner, self.index, py, |source, py| {
            let attached: &AttachedSource = &source.attached;
            Ok((
                attached.name.clone(),
                !attached.entry.bind(py).getattr("loader")?.is_none(),
                attached.database.clone(),
                attached.schema.clone(),
            ))
        })
    }
}

/// One assembled source, read from the compiled project that owns it.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeCompiledSource {
    owner: Py<NativeCompiledProject>,
    index: usize,
}

impl NativeCompiledSource {
    pub(crate) fn new(owner: Py<NativeCompiledProject>, index: usize) -> Self {
        Self { owner, index }
    }
}

#[pymethods]
impl NativeCompiledSource {
    /// The source's planner-facing `CompiledObjectKey`.
    #[getter]
    fn key(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let classes: InputViewClasses<'_> = view_classes(&self.owner, py)?;
        read_source(&self.owner, self.index, py, |source, py| {
            source
                .key
                .get_or_try_init(py, || {
                    object_key(&classes.compiled, SOURCE_RESOURCE, &source.attached.name)
                })
                .map(|key| key.clone_ref(py))
        })
    }

    #[getter]
    fn deps<'py>(&self, py: Python<'py>) -> Bound<'py, PyTuple> {
        PyTuple::empty(py)
    }

    #[getter]
    fn name(&self, py: Python<'_>) -> PyResult<String> {
        read_source(&self.owner, self.index, py, |source, _| {
            Ok(source.attached.name.clone())
        })
    }

    #[getter]
    fn source_entry(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        read_source(&self.owner, self.index, py, |source, py| {
            source.assembled_entry(py)
        })
    }

    #[getter]
    fn source_file(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        read_source(&self.owner, self.index, py, |source, py| {
            Ok(source.attached.source_file.clone_ref(py))
        })
    }
}

/// Keep `attached` in `owner`; return each source's view.
pub(crate) fn retain_sources(
    owner: &Bound<'_, NativeCompiledProject>,
    attached: Vec<AttachedSource>,
) -> Vec<NativeSourceInput> {
    let mut project = owner.borrow_mut();
    let first: usize = project.sources().len();
    let count: usize = attached.len();
    for source in attached {
        project.retain_source(SourceRecord::new(source));
    }
    drop(project);
    (first..first + count)
        .map(|index| NativeSourceInput::new(owner.clone().unbind(), index))
        .collect()
}
