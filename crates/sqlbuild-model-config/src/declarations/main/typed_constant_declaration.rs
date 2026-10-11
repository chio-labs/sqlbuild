//! Python's `typed_constant_declaration` for a constant file entry.

use crate::declarations::_helpers::values::typed_constant;
use crate::declarations::errors::DeclarationFailure;
use crate::declarations::models::ConstantFacts;
use crate::sql_values::models::RawSqlValue;

/// The typed value of constant `name` with its optional explicit type and rendering.
pub fn typed_constant_declaration(
    name: &str,
    raw: &RawSqlValue,
    options: (Option<&str>, Option<&str>),
    file_path: &str,
) -> Result<ConstantFacts, DeclarationFailure> {
    typed_constant(name, raw, options, file_path)
}
