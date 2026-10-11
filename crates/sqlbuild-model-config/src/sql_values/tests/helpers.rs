use sqlbuild_core::models::{SqlLogicalType, SqlValueKind};

/// The logical type of an integer.
pub(super) fn integer_type() -> SqlLogicalType {
    SqlLogicalType {
        kind: SqlValueKind::Integer,
        element_type: None,
    }
}
