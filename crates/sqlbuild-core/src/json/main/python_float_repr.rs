//! Python's `repr(float)`.

/// `repr(value)`, including `nan`, `inf` and `-inf`.
pub fn python_float_repr(value: f64) -> String {
    crate::json::_helpers::floats::python_repr(value)
}
