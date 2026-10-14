//! Migration rows using the shared plan colors and layout.

use crate::cli_text::main::split_count_header::split_count_header;

use crate::cli_text::models::{CliStyle, ColumnMigrationText, MigrationText, OldNameText};
use crate::plan_display::constants::{
    MIGRATION_AUTOMATIC, MIGRATION_DONE, MIGRATION_INCOMPATIBLE, MIGRATION_MANUAL,
    MIGRATION_RENAMED, OLD_NAME_LIVE, OLD_NAME_NONE, OLD_NAME_VIEW_ONLY,
};
use crate::plan_display::main::old_name_rows::old_name_rows;

pub(crate) fn property_row(label: &str, value: &str, style: CliStyle) -> String {
    format!("    {}  {value}", style.muted(label))
}

pub(crate) fn old_name_facts(entry: &OldNameText) -> Vec<(&str, String)> {
    if entry.action == OLD_NAME_NONE {
        return vec![(
            "left for janitor",
            entry
                .reason
                .as_deref()
                .filter(|value| !value.is_empty())
                .unwrap_or("no compatibility view")
                .to_owned(),
        )];
    }
    let until = entry
        .expires_date
        .as_ref()
        .map_or_else(String::new, |date| format!("until {date}"));
    let view = if entry.action == OLD_NAME_LIVE {
        format!("live {until}").trim().to_owned()
    } else {
        until
    };
    let mut facts = vec![("view", view)];
    if !entry.column_aliases.is_empty() {
        facts.push((
            "columns",
            entry
                .column_aliases
                .iter()
                .map(|(old, new)| format!("{old} <- {new}"))
                .collect::<Vec<_>>()
                .join(", "),
        ));
    }
    if entry.grants_supported {
        let text = entry.grants_copied.as_ref().map_or_else(
            || "copied from the old table".to_owned(),
            |count| format!("{count} copied from the old table"),
        );
        facts.push(("grants", text));
    }
    facts.push((
        "old table",
        if entry.action == OLD_NAME_VIEW_ONLY {
            "already archived"
        } else {
            "archived"
        }
        .to_owned(),
    ));
    facts
}

fn decision_text(entry: &MigrationText, style: CliStyle) -> String {
    let decision = &entry.decision;
    if decision.blocks_build && decision.decision_blocks_build {
        return style.error_strong(&decision.label);
    }
    if decision.origin_missing
        || matches!(
            decision.value.as_str(),
            "superseded_replace" | "forced_replace"
        )
    {
        return style.warning_strong(&decision.label);
    }
    if decision.value == MIGRATION_DONE {
        return style.muted(&decision.label);
    }
    style.accent_strong(&decision.label)
}

pub(crate) fn migration_lines(
    entry: &MigrationText,
    old_name: Option<&OldNameText>,
    style: CliStyle,
    hint: &str,
) -> Vec<String> {
    let renamed = entry.decision.value == MIGRATION_RENAMED;
    let decision = if renamed {
        if entry.completed_at.is_some() {
            style.muted("done")
        } else {
            style.accent_strong("migrate")
        }
    } else {
        decision_text(entry, style)
    };
    let mut rows = vec![format!(
        "  {}  {decision}  {} {}",
        style.object_name(&entry.model_name),
        style.muted(&format!("{} ->", entry.origin)),
        entry.destination
    )];
    if renamed && entry.completed_at.is_none() {
        rows.push(property_row(
            "transfer",
            if entry.materialization.as_deref() == Some("view") {
                "recreate (view)"
            } else {
                "rebuild (table)"
            },
            style,
        ));
    }
    if entry.decision.checks_compatibility {
        let value = match entry.compatibility.as_str() {
            "compatible" => style.success(&entry.compatibility),
            "incompatible" => style.error(&entry.compatibility),
            _ => entry.compatibility.clone(),
        };
        rows.push(property_row("compatibility", &value, style));
    }
    if let Some(transfer) = &entry.transfer {
        let fallback = entry
            .transfer_fallback
            .as_ref()
            .map_or_else(String::new, |value| format!(" ({value} if refused)"));
        let mut details = vec![format!("{transfer}{fallback}")];
        if let Some(value) = &entry.storage_transition {
            details.push(value.clone());
        }
        if let Some(value) = &entry.promotion {
            details.push(format!("promote by {value}"));
        }
        rows.push(property_row(
            "transfer",
            &details
                .into_iter()
                .filter(|value| !value.is_empty())
                .collect::<Vec<_>>()
                .join(", "),
            style,
        ));
    }
    if entry.discovery != MIGRATION_MANUAL {
        rows.push(property_row("discovery", &entry.discovery, style));
    }
    if entry.discovery == MIGRATION_AUTOMATIC && entry.completed_at.is_none() {
        rows.push(property_row("hint", hint, style));
    }
    if let Some(completed) = &entry.completed_at {
        rows.push(property_row(
            "completed",
            &format!("{completed} on target '{}'", entry.target_label),
            style,
        ));
    }
    if let Some(old_name) = old_name {
        rows.extend(old_name_rows(old_name, style));
    }
    for finding in &entry.findings {
        let value = format!("! {finding}");
        let styled = if entry.decision.blocks_build || entry.compatibility == MIGRATION_INCOMPATIBLE
        {
            style.error(&value)
        } else {
            style.warning(&value)
        };
        rows.push(format!("    {styled}"));
    }
    rows
}

pub(crate) fn column_migration_text(entry: &ColumnMigrationText, style: CliStyle) -> String {
    let decision = &entry.decision;
    let styled = if decision.blocks_build {
        style.error_strong(&decision.label)
    } else if decision.origin_missing {
        style.warning_strong(&decision.label)
    } else if decision.value == MIGRATION_DONE {
        style.muted(&decision.label)
    } else {
        style.accent_strong(&decision.label)
    };
    let mut details: Vec<String> = Vec::new();
    if entry.discovery != MIGRATION_MANUAL {
        details.push(entry.discovery.clone());
    }
    if decision.value == MIGRATION_DONE
        && let Some(completed) = &entry.completed_at
    {
        details.push(format!("completed {completed}"));
    }
    let suffix = if details.is_empty() {
        String::new()
    } else {
        format!("  {}", style.muted(&format!("({})", details.join(", "))))
    };
    format!(
        "{} -> {}  {styled}{suffix}",
        entry.origin_column, entry.destination_column
    )
}
pub(crate) fn section_header(style: CliStyle, text: &str) -> String {
    if let Some((title, count)) = split_count_header(text) {
        return format!(
            "{} {}",
            style.plan_section(title),
            style.muted(&format!("({count}"))
        );
    }
    style.plan_section(text)
}
