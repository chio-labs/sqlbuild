//! Migration sections in planner order.

use crate::cli_text::main::format_overflow_line::format_overflow_line;
use crate::cli_text::models::{CliStyle, MigrationTextReport};
use crate::plan_display::_helpers::migration_sections::{
    column_migration_text, migration_lines, section_header,
};
use crate::plan_display::main::old_name_rows::old_name_rows;
use std::collections::{BTreeMap, BTreeSet};

/// Append model migrations, resumed old names and grouped column migrations.
pub fn format_model_migrations(
    mut lines: Vec<String>,
    report: &MigrationTextReport,
) -> Vec<String> {
    let style = CliStyle { use_color: true };
    let old_names: BTreeMap<_, _> = report
        .old_names
        .iter()
        .map(|entry| (&entry.model_name, entry))
        .collect();
    if !report.migrations.is_empty() {
        lines.push(section_header(
            style,
            &format!("Migrations ({})", report.migrations.len()),
        ));
        let visible = report
            .display
            .max_entries
            .map_or(report.migrations.len(), |limit| {
                limit.min(report.migrations.len())
            });
        for entry in &report.migrations[..visible] {
            lines.extend(migration_lines(
                entry,
                old_names.get(&entry.model_name).copied(),
                style,
                &report.manual_rename_hint,
            ));
        }
        lines.extend(format_overflow_line(
            (report.migrations.len() - visible) as i64,
            "  ",
            &report.display.overflow_flag,
        ));
    }
    let migrated: BTreeSet<_> = report
        .migrations
        .iter()
        .map(|entry| &entry.model_name)
        .collect();
    let resumed: Vec<_> = report
        .old_names
        .iter()
        .filter(|entry| !migrated.contains(&entry.model_name))
        .collect();
    if !resumed.is_empty() {
        lines.push(section_header(
            style,
            &format!("Old names ({})", resumed.len()),
        ));
        for entry in resumed {
            lines.push(format!(
                "  {}  {} {}",
                style.object_name(&entry.model_name),
                style.muted(&format!("{} ->", entry.origin)),
                entry.destination
            ));
            lines.extend(old_name_rows(entry, style));
        }
    }
    if !report.columns.is_empty() {
        lines.push(section_header(
            style,
            &format!("Column migrations ({})", report.columns.len()),
        ));
        let mut seen: BTreeSet<&str> = BTreeSet::new();
        for first in &report.columns {
            if !seen.insert(&first.model_name) {
                continue;
            }
            lines.push(format!(
                "  {}  {}",
                style.object_name(&first.model_name),
                style.muted("migrate columns")
            ));
            for entry in &report.columns {
                if entry.model_name == first.model_name {
                    lines.push(format!("    {}", column_migration_text(entry, style)));
                }
            }
        }
    }
    lines
}
