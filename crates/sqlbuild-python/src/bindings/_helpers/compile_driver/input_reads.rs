//! Environment, settings and run-identity reads templates make during one compile.

use std::collections::BTreeSet;
use std::sync::{Mutex, MutexGuard, PoisonError};

use pyo3::prelude::{Bound, Py, PyAny, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::PyTuple;
use pyo3::{pyclass, pymethods};

#[derive(Default)]
struct Reads {
    environment_names: BTreeSet<String>,
    read_run_id: bool,
    settings_classes: Vec<Py<PyAny>>,
}

/// Environment, settings, and run-identity reads observed during one compile.
#[pyclass(frozen, module = "sqlbuild._native")]
pub(crate) struct CompileInputReads {
    reads: Mutex<Reads>,
}

impl CompileInputReads {
    fn locked(&self) -> MutexGuard<'_, Reads> {
        self.reads.lock().unwrap_or_else(PoisonError::into_inner)
    }
}

#[pymethods]
impl CompileInputReads {
    #[new]
    fn new() -> Self {
        Self {
            reads: Mutex::new(Reads::default()),
        }
    }

    /// Record one environment variable a template looked up, present or not.
    fn add_environment_name(&self, name: String) {
        self.locked().environment_names.insert(name);
    }

    /// Record one settings class whose values come from the environment or files.
    fn add_settings_class(&self, settings_class: &Bound<'_, PyAny>) {
        let mut reads: MutexGuard<'_, Reads> = self.locked();
        if !reads
            .settings_classes
            .iter()
            .any(|known| known.is(settings_class))
        {
            reads.settings_classes.push(settings_class.clone().unbind());
        }
    }

    /// Record that a template read the per-invocation run identity.
    fn mark_run_id_read(&self) {
        self.locked().read_run_id = true;
    }

    /// The recorded environment variable names in sorted order.
    #[getter]
    fn environment_names<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(py, self.locked().environment_names.iter())
    }

    /// The recorded settings classes in discovery order.
    #[getter]
    fn settings_classes<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        let classes: Vec<Py<PyAny>> = self
            .locked()
            .settings_classes
            .iter()
            .map(|class| class.clone_ref(py))
            .collect();
        PyTuple::new(py, classes)
    }

    /// Whether any template read the per-invocation run identity.
    #[getter]
    fn read_run_id(&self) -> bool {
        self.locked().read_run_id
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<CompileInputReads>()
}
