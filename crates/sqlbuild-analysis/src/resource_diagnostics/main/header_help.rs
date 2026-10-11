//! The help that shows the header entry describing a SQL-authored resource.

use crate::contracts::main::snippet_help::snippet_help;
use crate::resource_diagnostics::models::HeaderHelp;

/// `to describe <kind> '<name>', add this to the <STATEMENT> header in <path>:` and its lines.
#[must_use]
pub fn header_help(help: &HeaderHelp<'_>) -> String {
    let lines: Vec<String> = if help.description_only {
        vec![format!("{} ({});", help.statement, help.entry)]
    } else {
        vec![
            format!("{} (", help.statement),
            format!("  {},", help.entry),
            "  ...".to_owned(),
            ");".to_owned(),
        ]
    };
    snippet_help(
        &format!("to describe {} '{}'", help.kind, help.name),
        &format!("add this to the {} header in {}", help.statement, help.path),
        &lines,
    )
}
