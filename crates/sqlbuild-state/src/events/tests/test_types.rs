use crate::events::errors::StateSqlError;
use crate::events::models::StateCell;

pub(crate) struct InsertTestCase {
    pub(crate) description: &'static str,
    pub(crate) cells: Vec<StateCell>,
    pub(crate) expected_sql: Result<String, StateSqlError>,
}
