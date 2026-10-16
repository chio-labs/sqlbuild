//! Derive fixture schema facts from relation metadata.

use crate::planner_fixtures::models::{FixtureColumn, FixtureSchema};

/// Collect authoritative folded names and last-declared known column types.
pub fn fixture_schema(columns: &[FixtureColumn], authoritative: bool) -> FixtureSchema {
    let mut expected_types: Vec<(String, String)> = Vec::new();
    for column in columns {
        if let Some(sql_type) = &column.sql_type {
            match expected_types
                .iter_mut()
                .find(|(name, _)| *name == column.folded_name)
            {
                Some((_, existing)) => existing.clone_from(sql_type),
                None => expected_types.push((column.folded_name.clone(), sql_type.clone())),
            }
        }
    }
    FixtureSchema {
        authoritative_names: authoritative.then(|| {
            columns
                .iter()
                .map(|column| column.folded_name.clone())
                .collect()
        }),
        expected_types,
    }
}
