use crate::state_tables::models::TableColumn;

/// One declared column of a test table.
pub(crate) fn column(name: &str, rendered_type: &str, required: bool) -> TableColumn {
    TableColumn {
        name: name.to_owned(),
        rendered_type: rendered_type.to_owned(),
        required,
    }
}
