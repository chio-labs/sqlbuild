//! Static collection-versus-scalar fixture type conflicts.

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::planner_fixtures::constants::COLLECTION_TYPES;

/// Whether exactly one of two known fixture types is a collection type.
pub fn collection_mismatch(expected: Option<&str>, inferred: Option<&str>) -> bool {
    let (Some(expected), Some(inferred)) = (expected, inferred) else {
        return false;
    };
    is_collection(expected) != is_collection(inferred)
}

fn is_collection(sql_type: &str) -> bool {
    let upper = sql_type.to_uppercase();
    let base = python_strip(upper.split('(').next().unwrap_or_default());
    COLLECTION_TYPES.contains(&base)
}
