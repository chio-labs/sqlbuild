use crate::state_tables::models::TableColumn;

pub(crate) struct CreateTableTestCase {
    pub(crate) description: &'static str,
    pub(crate) columns: Vec<TableColumn>,
    pub(crate) expected_sql: &'static str,
}

pub(crate) struct ValuesInsertTestCase {
    pub(crate) description: &'static str,
    pub(crate) rows: Vec<Vec<String>>,
    pub(crate) expected_sql: &'static str,
}
