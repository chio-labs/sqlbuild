//! The selected loader and source names before execution.

use crate::cli_text::models::CliStyle;
use crate::load_command::constants::{TREE_BRANCH_GLYPH, TREE_LAST_GLYPH};

fn names_section(title: &str, names: &[&str], style: CliStyle) -> String {
    let mut text: String = format!("{}\n", style.section(&format!("{title} ({})", names.len())));
    for (index, name) in names.iter().enumerate() {
        text.push_str(&format!(
            "{} {name}\n",
            style.muted(if index + 1 == names.len() {
                TREE_LAST_GLYPH
            } else {
                TREE_BRANCH_GLYPH
            })
        ));
    }
    text.push('\n');
    text
}

/// `Loaders (n)` when any intermediate loaders run, then `Sources (n)`, each as a tree.
#[must_use]
pub fn render_load_plan(entries: &[(String, bool)], style: CliStyle) -> String {
    let loaders: Vec<&str> = entries
        .iter()
        .filter(|(_, loader)| *loader)
        .map(|(name, _)| name.as_str())
        .collect();
    let sources: Vec<&str> = entries
        .iter()
        .filter(|(_, loader)| !*loader)
        .map(|(name, _)| name.as_str())
        .collect();
    let mut text: String = String::new();
    if !loaders.is_empty() {
        text.push_str(&names_section("Loaders", &loaders, style));
    }
    text.push_str(&names_section("Sources", &sources, style));
    text
}
