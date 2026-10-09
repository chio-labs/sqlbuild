//! Python's `types_equal` over the native type system, deferring where it cannot answer.

use crate::contracts::models::ContractDeferral;
use crate::type_system::main::normalize_type::normalize_type;
use crate::type_system::models::{NormalizedType, TypeNormalization};

/// Whether two type strings normalize to the same comparison shape.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum TypeComparison {
    Equal,
    Different,
}

/// Compare two types as Python's `types_equal`, or defer when either type has no native answer.
pub(crate) fn types_equal(
    left: &str,
    right: &str,
    dialect: &str,
) -> Result<TypeComparison, ContractDeferral> {
    let left: NormalizedType = normalized(left, dialect)?;
    let right: NormalizedType = normalized(right, dialect)?;
    Ok(if left == right {
        TypeComparison::Equal
    } else {
        TypeComparison::Different
    })
}

fn normalized(type_sql: &str, dialect: &str) -> Result<NormalizedType, ContractDeferral> {
    normalize_type(type_sql, dialect)
        .map(|TypeNormalization { normalized, .. }| normalized)
        .ok_or(ContractDeferral::TypeNormalization)
}
