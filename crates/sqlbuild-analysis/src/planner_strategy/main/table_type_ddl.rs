//! Logical table DDL for the model's table type.

use crate::planner_strategy::constants::{
    PERMANENT_TABLE_DDL, PERMANENT_TABLE_TYPE, TRANSIENT_TABLE_DDL,
};

/// The adapter's DDL, with its first transient table keyword dropped for permanent tables.
pub fn table_type_ddl(ddl: &str, table_type: &str) -> String {
    if table_type == PERMANENT_TABLE_TYPE {
        return ddl.replacen(TRANSIENT_TABLE_DDL, PERMANENT_TABLE_DDL, 1);
    }
    ddl.to_owned()
}
