//! Python methods of authored binding positions.

use crate::bindings::_helpers::panics::compiler_guard;
use crate::bindings::models::{BindingPositions, PositionInput};
use crate::semantic_validation::models as validation;
use pyo3::exceptions::PyValueError;
use pyo3::{PyResult, pymethods};

#[pymethods]
impl BindingPositions {
    #[new]
    fn new(request: PositionInput) -> PyResult<Self> {
        compiler_guard(|| {
            validation::BindingPositions::new(request.into())
                .map(|inner| Self { inner })
                .map_err(PyValueError::new_err)
        })
    }

    fn position(
        &self,
        start: Option<usize>,
        line: Option<usize>,
        column: Option<usize>,
        message: &str,
    ) -> PyResult<(Option<usize>, Option<usize>)> {
        compiler_guard(|| {
            self.inner
                .position(start, line, column, message)
                .map_err(PyValueError::new_err)
        })
    }
}
