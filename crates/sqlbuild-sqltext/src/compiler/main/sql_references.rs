//! Public compiler entry point for conservative logical SQL references.

use crate::compiler::types::StaticReference;

pub fn extract(sql: &str) -> Option<Vec<StaticReference>> {
    crate::compiler::_helpers::sql_references::extraction::extract(sql)
}
