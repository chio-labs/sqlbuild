//! `event_cells`: one event row's values with their declared state column types.

use crate::events::constants::TIMESTAMP_COLUMNS;
use crate::events::models::{StateCell, StateColumnType, StateValue};

/// Pair each column with its value, typing `expires_at` and `created_at` as text timestamps.
#[must_use]
pub fn event_cells(columns: &[&str], values: Vec<StateValue>) -> Vec<StateCell> {
    columns
        .iter()
        .zip(values)
        .map(|(column, value)| StateCell {
            column: (*column).to_owned(),
            column_type: if TIMESTAMP_COLUMNS.contains(column) {
                StateColumnType::TextTimestamp
            } else {
                StateColumnType::String
            },
            value,
        })
        .collect()
}
