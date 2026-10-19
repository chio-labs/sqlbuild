//! `describe_store`: the store's views and tables with their columns.

use crate::store::_helpers::sqlite::checked;
use crate::store::errors::StoreError;
use crate::store::models::{DescribedColumn, DescribedRelation, SqliteStore};

/// Views first, then `recall_*` tables, each sorted by name.
pub fn describe_store(store: &SqliteStore) -> Result<Vec<DescribedRelation>, StoreError> {
    let mut statement = checked(
        store.connection.prepare(
            "SELECT name, type FROM sqlite_schema WHERE type IN ('table', 'view') \
             AND name NOT LIKE 'sqlite!_%' ESCAPE '!' ORDER BY type = 'table', name",
        ),
        "describe Recall store",
    )?;
    let relations: Vec<(String, String)> = checked(
        statement
            .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))
            .and_then(Iterator::collect),
        "describe Recall store",
    )?;
    let mut described = Vec::with_capacity(relations.len());
    for (name, kind) in relations {
        let mut columns = checked(
            store
                .connection
                .prepare("SELECT name, type, \"notnull\" FROM pragma_table_xinfo(?1)"),
            "describe Recall relation",
        )?;
        let columns: Vec<DescribedColumn> = checked(
            columns
                .query_map([&name], |row| {
                    Ok(DescribedColumn {
                        name: row.get(0)?,
                        declared_type: row.get(1)?,
                        nullable: row.get::<_, i64>(2)? == 0,
                    })
                })
                .and_then(Iterator::collect),
            "describe Recall relation",
        )?;
        described.push(DescribedRelation {
            name,
            kind,
            columns,
        });
    }
    Ok(described)
}
