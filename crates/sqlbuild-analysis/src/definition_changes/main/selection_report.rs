//! The lines a `--since` run prints about what changed and what it selected.

use crate::definition_changes::models::SelectedItem;

/// `Changed since <ref>: …`, then `Selected N of M <noun>` with each item's reasons when
/// `explain` is set, or the line saying nothing is affected.
pub fn selection_report(
    (reference, summary): (&str, &str),
    (singular, plural): (&str, &str),
    (total, selected): (usize, &[SelectedItem]),
    explain: bool,
) -> String {
    let mut text: String = format!("Changed since {reference}: {summary}\n");
    if selected.is_empty() {
        text.push_str(&format!(
            "No {plural} are affected by the changes since {reference}\n"
        ));
        return text;
    }
    let noun: &str = if total == 1 { singular } else { plural };
    text.push_str(&format!("Selected {} of {total} {noun}\n", selected.len()));
    if explain {
        for item in selected {
            text.push_str(&format!("  {}\n", item.label));
            for reason in &item.reasons {
                text.push_str(&format!("    {reason}\n"));
            }
        }
    }
    text
}
