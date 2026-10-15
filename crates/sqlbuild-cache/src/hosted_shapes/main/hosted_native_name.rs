//! The native class hosting one Python shape, found by its module and class name.

use crate::hosted_shapes::constants::{HOSTED_SHAPE_TYPES, NATIVE_MODULE};
use crate::hosted_shapes::errors::AmbiguousShapeName;

/// The native class name hosting `module:class`, or `None` when the shape is still Python.
pub fn hosted_native_name(
    module: &str,
    class: &str,
) -> Result<Option<&'static str>, AmbiguousShapeName> {
    let mut found: Option<&'static str> = None;
    for (native, python) in HOSTED_SHAPE_TYPES {
        if python.split_once(':') != Some((module, class)) {
            continue;
        }
        let Some(native_name) = native
            .strip_prefix(NATIVE_MODULE)
            .and_then(|rest| rest.strip_prefix(':'))
        else {
            continue;
        };
        if found.is_some_and(|existing| existing != native_name) {
            return Err(AmbiguousShapeName);
        }
        found = Some(native_name);
    }
    Ok(found)
}
