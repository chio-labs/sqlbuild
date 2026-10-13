//! Model and column migration gates and the old-name refusal.

use std::collections::BTreeSet;

use crate::build_command::constants::{
    COLUMN_BLOCK_CODES, COLUMN_BLOCK_DEFAULT_CODE, COLUMN_MIGRATION_HELP, HIDDEN_ORIGIN_REMEDY,
    MIGRATION_CODE, MIGRATION_CONFLICT, MIGRATION_CONFLICT_CODE, MIGRATION_CONFLICT_HELP,
    MIGRATION_INCOMPATIBLE_CODE, MIGRATION_INCOMPATIBLE_HELP, MIGRATION_ORIGIN_MISSING,
    MIGRATION_PLAN_HELP, OLD_NAME_CODES, OLD_NAME_DEFAULT_CODE, OLD_NAME_HELP,
};
use crate::build_command::errors::BuildCommandError;
use crate::build_command::models::{
    ColumnMigrationFact, Confirmation, ModelMigrationFact, PlanWarningFact,
};

fn origins(entries: &[&ModelMigrationFact]) -> String {
    entries
        .iter()
        .map(|entry| {
            format!(
                "'{}' (migrate_from {})",
                entry.model_name, entry.origin_label
            )
        })
        .collect::<Vec<String>>()
        .join(", ")
}

/// Refuse to build while any planned migration conflicts or is incompatible.
pub(crate) fn model_migration_refusal(entries: &[ModelMigrationFact]) -> Option<BuildCommandError> {
    let blocked: Vec<&ModelMigrationFact> =
        entries.iter().filter(|entry| entry.blocks_build).collect();
    if blocked.is_empty() {
        return None;
    }
    let hidden: Vec<&ModelMigrationFact> = blocked
        .iter()
        .copied()
        .filter(|entry| entry.origin_hidden)
        .collect();
    if !hidden.is_empty() {
        return Some(BuildCommandError::new(
            Some(MIGRATION_CODE),
            format!(
                "model migration origin was built in this target but is not visible for {}; {HIDDEN_ORIGIN_REMEDY}",
                origins(&hidden)
            ),
            Some(MIGRATION_PLAN_HELP),
        ));
    }
    let missing: Vec<&ModelMigrationFact> = blocked
        .iter()
        .copied()
        .filter(|entry| entry.decision == MIGRATION_ORIGIN_MISSING)
        .collect();
    if !missing.is_empty() {
        return Some(BuildCommandError::new(
            Some(MIGRATION_CODE),
            format!(
                "model migration origin does not exist for {} and no recorded migration into it was found, and this target sets missing_migration_origin = deny; if the migration already happened elsewhere or is no longer needed, remove migrate_from from the model header",
                origins(&missing)
            ),
            Some(MIGRATION_PLAN_HELP),
        ));
    }
    let names: String = blocked
        .iter()
        .map(|entry| format!("'{}'", entry.model_name))
        .collect::<Vec<String>>()
        .join(", ");
    if blocked
        .iter()
        .any(|entry| entry.decision == MIGRATION_CONFLICT)
    {
        return Some(BuildCommandError::new(
            Some(MIGRATION_CONFLICT_CODE),
            format!(
                "model migration conflict for {names}: the destination already exists with its own build history and no recorded migration"
            ),
            Some(MIGRATION_CONFLICT_HELP),
        ));
    }
    Some(BuildCommandError::new(
        Some(MIGRATION_INCOMPATIBLE_CODE),
        format!("model migration source is incompatible with {names}"),
        Some(MIGRATION_INCOMPATIBLE_HELP),
    ))
}

/// Refuse to build while any declared column rename cannot be applied safely.
pub(crate) fn column_migration_refusal(
    entries: &[ColumnMigrationFact],
) -> Option<BuildCommandError> {
    let blocked: Vec<&ColumnMigrationFact> =
        entries.iter().filter(|entry| entry.blocks_build).collect();
    let first: &ColumnMigrationFact = blocked.first()?;
    let code: &str = COLUMN_BLOCK_CODES
        .iter()
        .find(|(decision, _)| *decision == first.decision)
        .map_or(COLUMN_BLOCK_DEFAULT_CODE, |(_, code)| code);
    let listed: String = blocked
        .iter()
        .map(|entry| {
            format!(
                "'{}' ({} migrate_from {}: {})",
                entry.model_name,
                entry.destination_column,
                entry.origin_column,
                entry.decision_label
            )
        })
        .collect::<Vec<String>>()
        .join(", ");
    Some(BuildCommandError::new(
        Some(code),
        format!("column migrations are blocked for {listed}"),
        Some(COLUMN_MIGRATION_HELP),
    ))
}

/// Confirm before building past declared migrations whose origin is missing.
pub(crate) fn missing_origin_confirmation(
    (models, columns): (&[ModelMigrationFact], &[ColumnMigrationFact]),
    help: &str,
) -> Option<Confirmation> {
    let mut names: BTreeSet<&str> = BTreeSet::new();
    for entry in models {
        if entry.origin_missing && !entry.blocks_build && entry.confirm_missing_origin {
            names.insert(&entry.model_name);
        }
    }
    for entry in columns {
        if entry.origin_missing && !entry.blocks_build && entry.confirm_missing_origin {
            names.insert(&entry.model_name);
        }
    }
    let first: &str = names.iter().next()?;
    let listed: String = names
        .iter()
        .map(|name| format!("'{name}'"))
        .collect::<Vec<String>>()
        .join(", ");
    let action: String = format!("building {listed} without its missing migrate_from origin");
    let expected: String = if names.len() == 1 {
        format!("build {first} without its migration")
    } else {
        format!("build {} models without their migrations", names.len())
    };
    Some(Confirmation {
        warning: format!(
            "The migrate_from origin of {listed} does not exist in this target; nothing will be migrated."
        ),
        expected,
        refusal: BuildCommandError::new(
            Some(MIGRATION_CODE),
            format!("{action} requires confirmation"),
            Some(help),
        ),
        cancellation: BuildCommandError::new(
            Some(MIGRATION_CODE),
            format!("{action} cancelled"),
            None,
        ),
    })
}

/// Refuse to build over a compatibility view or while code reads an old name.
pub(crate) fn old_name_refusal(warnings: &[PlanWarningFact]) -> Option<BuildCommandError> {
    let errors: Vec<&PlanWarningFact> = warnings
        .iter()
        .filter(|warning| {
            warning
                .code
                .as_deref()
                .is_some_and(|code| OLD_NAME_CODES.contains(&code))
        })
        .collect();
    let first: &PlanWarningFact = errors.first()?;
    Some(BuildCommandError::new(
        Some(first.code.as_deref().unwrap_or(OLD_NAME_DEFAULT_CODE)),
        errors
            .iter()
            .map(|warning| warning.message.as_str())
            .collect::<Vec<&str>>()
            .join("; "),
        Some(OLD_NAME_HELP),
    ))
}
