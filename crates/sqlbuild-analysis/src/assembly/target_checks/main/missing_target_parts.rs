//! The parts of a relation location execution needs but the location lacks.

use crate::assembly::target_checks::constants::{DATABASE_PART, SCHEMA_PART};

/// `database` and then `schema`, each when it is missing.
pub fn missing_target_parts(database: Option<&str>, schema: Option<&str>) -> Vec<&'static str> {
    let mut missing: Vec<&'static str> = Vec::new();
    if database.is_none() {
        missing.push(DATABASE_PART);
    }
    if schema.is_none() {
        missing.push(SCHEMA_PART);
    }
    missing
}
