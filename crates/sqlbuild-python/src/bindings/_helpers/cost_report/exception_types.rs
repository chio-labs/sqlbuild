//! Cost observability exceptions.

use pyo3::create_exception;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};

create_exception!(
    sqlbuild._native,
    CostArtifactError,
    PyValueError,
    "Raised when a persisted cost artifact has an invalid shape."
);

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add(
        "CostArtifactError",
        module.py().get_type::<CostArtifactError>(),
    )
}
