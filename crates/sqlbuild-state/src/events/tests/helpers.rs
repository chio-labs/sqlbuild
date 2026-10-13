use crate::events::models::{StateCell, StateColumnType, StateValue};

pub(crate) fn cell(column: &str, column_type: StateColumnType, value: StateValue) -> StateCell {
    StateCell {
        column: column.to_owned(),
        column_type,
        value,
    }
}
