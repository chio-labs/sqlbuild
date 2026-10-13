//! `event_insert_sql`: one append-only event row as `INSERT ... VALUES` with typed literals.

use crate::events::_helpers::literals::literal;
use crate::events::errors::StateSqlError;
use crate::events::models::StateCell;

/// `INSERT INTO <table> (<columns>) VALUES (<literals>)`, failing on the first ill-typed value.
pub fn event_insert_sql(table: &str, cells: &[StateCell]) -> Result<String, StateSqlError> {
    let literals: Vec<String> = cells
        .iter()
        .map(|cell| literal(cell.column_type, &cell.value))
        .collect::<Result<_, _>>()?;
    let columns: Vec<&str> = cells.iter().map(|cell| cell.column.as_str()).collect();
    Ok(format!(
        "INSERT INTO {table} ({}) VALUES ({})",
        columns.join(", "),
        literals.join(", ")
    ))
}
