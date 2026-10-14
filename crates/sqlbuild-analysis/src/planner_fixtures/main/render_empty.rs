//! Adapter-independent empty-fixture projection SQL.

use crate::planner_fixtures::models::FixtureColumn;

/// Render the validated authoritative empty-fixture schema.
pub fn render_empty<E>(
    columns: &[FixtureColumn],
    mut render: impl FnMut(&str) -> Result<String, E>,
) -> Result<String, E> {
    let mut projections: Vec<String> = Vec::new();
    for column in columns {
        let name = render(&column.name)?;
        projections.push(format!(
            "CAST(NULL AS {}) AS {name}",
            column.sql_type.as_deref().unwrap_or("None")
        ));
    }
    Ok(format!(
        "SELECT\n  {}\nWHERE FALSE",
        projections.join(",\n  ")
    ))
}
