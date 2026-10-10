//! Validate a model's column renames before they are attached to its schema entry.

use crate::errors::ConfigError;
use crate::model_validation::_helpers::materialization::{
    chained_problem, column_materialization_problem, origin_problem,
};
use crate::model_validation::models::ColumnMigration;

/// The first problem with the columns' `migrate_from` declarations, if any.
pub fn validate_column_migrations(
    model_name: &str,
    materialized: Option<&str>,
    model_migrates: bool,
    columns: &[ColumnMigration],
) -> Result<(), ConfigError> {
    let mut declared: Vec<(&str, &str)> = Vec::new();
    for column in columns {
        if let Some(origin) = column.migrate_from.as_deref() {
            declared.push((column.name.as_str(), origin));
        }
    }
    let Some(&(first, _)) = declared.first() else {
        return Ok(());
    };
    column_materialization_problem(model_name, materialized, model_migrates, first)?;
    origin_problem(model_name, &declared)?;
    chained_problem(model_name, &declared)
}
