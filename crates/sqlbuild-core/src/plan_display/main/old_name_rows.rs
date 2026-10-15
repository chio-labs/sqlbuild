//! Render an old relation name and its nested facts.

use crate::cli_text::main::format_tree_connector::format_tree_connector as tree_connector;
use crate::cli_text::models::{CliStyle, OldNameText};
use crate::plan_display::_helpers::migration_sections::{old_name_facts, property_row};

/// Render the old name as a leaf with one fact per nested row.
pub fn old_name_rows(entry: &OldNameText, style: CliStyle) -> Vec<String> {
    let facts = old_name_facts(entry);
    let mut rows = vec![property_row("old name", &entry.origin, style)];
    for (index, (label, value)) in facts.iter().enumerate() {
        rows.push(format!(
            "        {} {}  {value}",
            tree_connector(style, index + 1 == facts.len()),
            style.muted(label)
        ));
    }
    rows
}
