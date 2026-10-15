//! Shared builders for janitor planning tests.

use crate::janitor_planning::models::OriginKey;

/// An origin key in one schema.
pub(super) fn key(database: Option<&str>, schema: &str, name: &str) -> OriginKey {
    OriginKey {
        database: database.map(str::to_owned),
        schema: Some(schema.to_owned()),
        name: name.to_owned(),
    }
}
