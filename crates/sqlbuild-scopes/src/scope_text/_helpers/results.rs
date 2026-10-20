//! The text of one scope report, folder browse or declaration list.

use std::collections::HashSet;

use sqlbuild_core::cli_text::models::CliStyle;

use crate::scope_report::models::{
    BrowseResult, DeclarationReport, ListResult, ScopeReport, ScopeSection,
};
use crate::scope_text::_helpers::declarations::{
    DeclarationStyle, declaration_lines, explanation_lines, move_lines,
};
use crate::scope_text::_helpers::layout::{
    FollowUp, completeness_line, connector, count_noun, diagnostic_lines, display_path, field,
    follow_up, none_line, plain_header, scope_label, section_count,
};
use crate::scope_text::constants::{LEGEND_MARKERS, LEGEND_VERBOSE_HINT};
use crate::scope_text::models::ScopeTextRequest;

fn joined(lines: Vec<String>) -> String {
    format!("{}\n", lines.join("\n"))
}

fn report_section<'a>(report: &'a ScopeReport, name: &str) -> Option<&'a ScopeSection> {
    report.sections.iter().find(|section| section.name == name)
}

fn header_lines(
    (style, request): (CliStyle, &ScopeTextRequest),
    report: &ScopeReport,
) -> Vec<String> {
    let resource = &report.resource;
    let mut lines: Vec<String> = vec![
        style.section("Scope"),
        field(style, "Target", &resource.target),
    ];
    if let Some(identity) = &resource.identity {
        lines.push(field(style, "Resource", identity));
    }
    if let Some(path) = &resource.path {
        lines.push(field(
            style,
            "Path",
            &display_path(Some(path), &request.paths),
        ));
    }
    let mut labels: Vec<String> = Vec::new();
    if resource.prospective {
        labels.push("prospective".to_owned());
    }
    if resource.directory {
        labels.push("directory".to_owned());
    }
    if resource.duplicate_count != 0 {
        labels.push(count_noun(resource.duplicate_count, "match", "matches"));
    }
    if !labels.is_empty() {
        lines.push(field(style, "Status", &labels.join(", ")));
    }
    lines
}

fn chain_lines(
    (style, request): (CliStyle, &ScopeTextRequest),
    report: &ScopeReport,
) -> Vec<String> {
    let mut lines: Vec<String> = vec![String::new(), style.section("Scope chain")];
    if report.scope_chain.is_empty() {
        lines.push(none_line(style));
    }
    for (index, entry) in report.scope_chain.iter().enumerate() {
        let path: String = display_path(Some(&entry.path), &request.paths);
        lines.push(format!(
            "  {} {} {}",
            connector(style, index == report.scope_chain.len() - 1),
            scope_label(&entry.kind),
            style.muted(&format!("{path} ({})", entry.declaration_count))
        ));
    }
    lines
}

/// One availability section: its title, declarations, report section name and whether optional.
struct AvailabilityGroup<'a> {
    title: &'a str,
    declarations: &'a [DeclarationReport],
    name: &'a str,
    optional: bool,
}

fn availability_lines(
    (style, request): (CliStyle, &ScopeTextRequest),
    report: &ScopeReport,
    used: &HashSet<String>,
) -> Vec<String> {
    let groups: [AvailabilityGroup<'_>; 3] = [
        AvailabilityGroup {
            title: "Available",
            declarations: &report.available,
            name: "available",
            optional: false,
        },
        AvailabilityGroup {
            title: "Relationship grants",
            declarations: &report.relationship_scope,
            name: "relationship_scope",
            optional: true,
        },
        AvailabilityGroup {
            title: "Nearby unavailable",
            declarations: &report.nearby_unavailable,
            name: "nearby_unavailable",
            optional: true,
        },
    ];
    let mut lines: Vec<String> = Vec::new();
    for AvailabilityGroup {
        title,
        declarations,
        name,
        optional,
    } in groups
    {
        let section: Option<&ScopeSection> = report_section(report, name);
        let collapsed_count: i64 = section.map_or(0, |section| section.collapsed_count);
        if optional && !request.verbose && declarations.is_empty() && collapsed_count == 0 {
            continue;
        }
        lines.push(String::new());
        lines.push(plain_header(
            style,
            title,
            &section_count(section, declarations.len()),
        ));
        lines.extend(declaration_lines(
            (style, request),
            declarations,
            &DeclarationStyle::marking(used),
        ));
        if collapsed_count != 0 {
            let globals: String = count_noun(collapsed_count, "global", "globals");
            let command: String = follow_up(
                request,
                FollowUp {
                    globals_all: true,
                    ..FollowUp::default()
                },
            );
            lines.push(format!(
                "  {}",
                style.muted(&format!("\u{2026} {globals} collapsed; run {command}"))
            ));
        }
    }
    lines
}

/// The report of one target: used, scope chain, available declarations and previews.
pub(crate) fn report_text(
    (style, request): (CliStyle, &ScopeTextRequest),
    report: &ScopeReport,
) -> String {
    let mut lines: Vec<String> = header_lines((style, request), report);
    let used: HashSet<String> = report
        .used
        .iter()
        .map(|item| item.identity.clone())
        .collect();
    lines.push(String::new());
    lines.push(plain_header(
        style,
        "Used",
        &format!("({})", report.used.len()),
    ));
    lines.extend(declaration_lines(
        (style, request),
        &report.used,
        &DeclarationStyle::marking(&used),
    ));
    lines.extend(chain_lines((style, request), report));
    lines.extend(availability_lines((style, request), report, &used));
    if let Some(explanation) = &report.explanation {
        lines.push(String::new());
        lines.push(style.section("Explanation"));
        match &explanation.declaration {
            None => lines.push(format!("  {}", style.muted("(declaration not resolved)"))),
            Some(declaration) => {
                lines.extend(explanation_lines((style, request), declaration, &used));
            }
        }
    }
    if let Some(preview) = &report.move_preview {
        lines.push(String::new());
        lines.extend(move_lines((style, request), preview, &used));
    }
    if !request.verbose {
        lines.push(String::new());
        lines.push(style.muted(&format!("{LEGEND_MARKERS}   {LEGEND_VERBOSE_HINT}")));
    }
    lines.push(String::new());
    lines.extend(diagnostic_lines(
        style,
        &report.diagnostics,
        request.verbose,
    ));
    lines.push(completeness_line(style, report.complete));
    joined(lines)
}

/// The child definition folders of one folder, with follow-up commands for each.
pub(crate) fn browse_text(
    (style, request): (CliStyle, &ScopeTextRequest),
    result: &BrowseResult,
) -> String {
    let mut lines: Vec<String> = vec![
        style.section("Scope folders"),
        field(
            style,
            "Path",
            &display_path(Some(&result.folder), &request.paths),
        ),
        String::new(),
    ];
    if result.folders.is_empty() {
        lines.push(none_line(style));
    }
    for (index, folder) in result.folders.iter().enumerate() {
        let kinds: Vec<String> = folder
            .kind_counts
            .iter()
            .map(|(kind, count)| format!("{kind} {count}"))
            .collect();
        let kinds: String = if kinds.is_empty() {
            "no declarations".to_owned()
        } else {
            kinds.join(", ")
        };
        let counts: String = format!(
            "{}, {} used, {}; {kinds}",
            count_noun(folder.descendant_count, "declaration", "declarations"),
            folder.used_count,
            count_noun(folder.child_count, "child", "children"),
        );
        lines.push(format!(
            "  {} {}/  {}",
            connector(style, index == result.folders.len() - 1),
            folder.name,
            style.muted(&counts)
        ));
        for extra in [
            FollowUp {
                browse: Some(&folder.path),
                ..FollowUp::default()
            },
            FollowUp {
                list_path: Some(&folder.path),
                ..FollowUp::default()
            },
        ] {
            lines.push(format!("     {}", style.muted(&follow_up(request, extra))));
        }
    }
    lines.push(String::new());
    lines.extend(diagnostic_lines(
        style,
        &result.diagnostics,
        request.verbose,
    ));
    lines.push(completeness_line(style, result.complete));
    joined(lines)
}

/// One page of declarations beneath a folder, with the command that continues it.
pub(crate) fn list_text(
    (style, request): (CliStyle, &ScopeTextRequest),
    result: &ListResult,
) -> String {
    let section: &ScopeSection = &result.section;
    let mut lines: Vec<String> = vec![
        style.section("Scope declarations"),
        field(
            style,
            "Path",
            &display_path(Some(&result.folder), &request.paths),
        ),
        field(
            style,
            "Showing",
            &format!("{} of {}", section.returned, section.total),
        ),
        String::new(),
    ];
    let unused: HashSet<String> = HashSet::new();
    lines.extend(declaration_lines(
        (style, request),
        &result.declarations,
        &DeclarationStyle::marking(&unused),
    ));
    if let Some(cursor) = &section.next_cursor {
        let command: String = follow_up(
            request,
            FollowUp {
                list_path: Some(&result.folder),
                after: Some(cursor),
                ..FollowUp::default()
            },
        );
        lines.push(String::new());
        lines.push(format!("{} {command}", style.muted("Continue:")));
    }
    if !request.verbose && !result.declarations.is_empty() {
        lines.push(String::new());
        lines.push(style.muted(LEGEND_VERBOSE_HINT));
    }
    lines.push(String::new());
    lines.extend(diagnostic_lines(
        style,
        &result.diagnostics,
        request.verbose,
    ));
    lines.push(completeness_line(style, section.complete));
    joined(lines)
}
