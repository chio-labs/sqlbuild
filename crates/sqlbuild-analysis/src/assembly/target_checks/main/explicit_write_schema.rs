//! `_optional_explicit_schema`: a schema that names a physical write schema.

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::assembly::target_checks::constants::PRESERVE_TARGET_VALUE;

/// The stripped schema, unless it is blank or `preserve`.
pub fn explicit_write_schema(value: Option<&str>) -> Option<String> {
    let schema: &str = python_strip(value?);
    (!schema.is_empty() && schema != PRESERVE_TARGET_VALUE).then(|| schema.to_owned())
}
