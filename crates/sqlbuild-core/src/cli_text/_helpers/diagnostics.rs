//! A diagnostic's human text: header, resource, located source with carets, notes and help.

use crate::cli_text::models::{CliStyle, DiagnosticText, LocationText};
use crate::text::main::python_splitlines::python_splitlines;

const ERROR_SEVERITY: &str = "error";
const WARNING_SEVERITY: &str = "warning";
const MODEL_RESOURCE: &str = "model";

/// Every shown diagnostic, separated by blank lines, with folded warning counts.
pub(crate) fn diagnostics_text(diagnostics: &[DiagnosticText], style: CliStyle) -> String {
    let mut lines: Vec<String> = Vec::new();
    for diagnostic in diagnostics {
        lines.extend(diagnostic_lines(diagnostic, style));
        if diagnostic.occurrences > 1 {
            lines.push(format!(
                "  = {} occurrences; all retained in JSON and the warning count",
                diagnostic.occurrences
            ));
        }
        lines.push(String::new());
    }
    let _ = lines.pop();
    lines.join("\n")
}

fn diagnostic_lines(diagnostic: &DiagnosticText, style: CliStyle) -> Vec<String> {
    let header: String = format!(
        "{}[{}]: {}",
        diagnostic.severity, diagnostic.code, diagnostic.message
    );
    let mut lines: Vec<String> = vec![match diagnostic.severity.as_str() {
        ERROR_SEVERITY => style.error(&header),
        WARNING_SEVERITY => style.warning(&header),
        _ => style.muted(&header),
    }];
    if let Some(resource) = &diagnostic.resource_name {
        let label: String = match &diagnostic.resource_type {
            Some(kind) if kind != MODEL_RESOURCE => kind.replace('_', " "),
            _ => MODEL_RESOURCE.to_owned(),
        };
        lines.push(format!("  {label}: {}", style.object_name(resource)));
    }
    if let Some(location) = &diagnostic.location {
        lines.extend(location_block(location, None));
    } else if let Some(path) = &diagnostic.path {
        lines.push(format!("  --> {path}"));
    }
    for related in &diagnostic.related {
        lines.push(String::new());
        lines.push(format!("  {}:", related.label));
        lines.extend(location_block(
            &related.location,
            related.message.as_deref(),
        ));
    }
    lines.extend(
        diagnostic
            .notes
            .iter()
            .map(|note| format!("  {} {note}", style.muted("= note:"))),
    );
    if !diagnostic.affected_rules.is_empty() {
        lines.push(format!(
            "  {} {}",
            style.muted("= affected Rules:"),
            diagnostic.affected_rules.join(", ")
        ));
    }
    if let Some(help) = &diagnostic.help {
        lines.push(format!("  {} {help}", style.muted("= help:")));
    }
    lines
}

/// `  --> path:line:column`, then the source line with carets when the line exists.
fn location_block(location: &LocationText, message: Option<&str>) -> Vec<String> {
    let mut lines: Vec<String> = vec![format!(
        "  --> {}:{}:{}",
        location.path, location.line, location.column
    )];
    let Some(source) = &location.source else {
        return lines;
    };
    let source_lines: Vec<&str> = python_splitlines(source);
    let Ok(line_index) = usize::try_from(location.line) else {
        return lines;
    };
    if !(1..=source_lines.len()).contains(&line_index) {
        return lines;
    }
    let source_line: &str = source_lines[line_index - 1];
    let line_number: String = location.line.to_string();
    let gutter: String = " ".repeat(line_number.chars().count());
    lines.push(format!("  {gutter} |"));
    lines.push(format!("  {line_number} | {source_line}"));
    lines.push(format!(
        "  {gutter} | {}",
        caret_line(location, source_line, message)
    ));
    lines
}

fn caret_line(location: &LocationText, source_line: &str, message: Option<&str>) -> String {
    let start_column: i64 = location.column.max(1);
    let mut end_column: i64 = match location.end_column {
        Some(column) if column != 0 => column,
        _ => start_column + 1,
    };
    if location
        .end_line
        .is_some_and(|end_line| end_line != location.line)
    {
        end_column = i64::try_from(source_line.chars().count()).unwrap_or(i64::MAX) + 1;
    }
    let caret_count: i64 = (end_column - start_column).max(1);
    let suffix: String = message.map_or_else(String::new, |message| format!(" {message}"));
    format!(
        "{}{}{suffix}",
        " ".repeat(usize::try_from(start_column - 1).unwrap_or_default()),
        "^".repeat(usize::try_from(caret_count).unwrap_or_default())
    )
}
