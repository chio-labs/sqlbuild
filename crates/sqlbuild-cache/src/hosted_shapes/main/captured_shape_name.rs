//! The Python shape name a natively hosted class is captured as.

use crate::hosted_shapes::constants::HOSTED_SHAPE_TYPES;

/// The `module:qualname` the native class `native` is captured as, when it hosts a Python shape.
pub fn captured_shape_name(native: &str) -> Option<&'static str> {
    HOSTED_SHAPE_TYPES
        .iter()
        .find(|(hosted, _)| *hosted == native)
        .map(|(_, python)| *python)
}
