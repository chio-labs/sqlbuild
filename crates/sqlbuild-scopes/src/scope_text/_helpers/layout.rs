//! Fields, headers, connectors, paths and follow-up commands of scope text output.

use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_core::shell_text::main::shell_quote::shell_quote;

use crate::scope_report::models::{DiagnosticFacts, ReportDiagnostic, ScopeSection};
use crate::scope_text::constants::{
    BRANCH_CONNECTOR, CURRENT_DIRECTORY, DEFAULT_PAGE_SIZE, ERROR_SEVERITY, GLOBAL_ALL,
    GLOBAL_SUMMARY, LAST_CONNECTOR, NONE_TEXT, PATH_COMPACT, PATH_NONE, PATH_RELATIVE,
    SCOPE_LABELS,
};
use crate::scope_text::models::ScopeTextRequest;
use crate::scope_text::types::Styler;

/// `  Label: value`.
pub(crate) fn field(style: CliStyle, label: &str, value: &str) -> String {
    format!("  {} {value}", style.muted(&format!("{label}:")))
}

/// A section title with its count, each in its own style.
pub(crate) fn header(
    title: &str,
    count: &str,
    (title_style, count_style): (Styler<'_>, Styler<'_>),
) -> String {
    format!("{} {}", title_style(title), count_style(count))
}

/// A section title in the section style with a muted count.
pub(crate) fn plain_header(style: CliStyle, title: &str, count: &str) -> String {
    header(
        title,
        count,
        (&|text: &str| style.section(text), &|text: &str| {
            style.muted(text)
        }),
    )
}

pub(crate) fn connector(style: CliStyle, last: bool) -> String {
    style.muted(if last {
        LAST_CONNECTOR
    } else {
        BRANCH_CONNECTOR
    })
}

pub(crate) fn none_line(style: CliStyle) -> String {
    format!("  {}", style.muted(NONE_TEXT))
}

/// The label a scope kind reads as.
pub(crate) fn scope_label(scope: &str) -> String {
    SCOPE_LABELS
        .iter()
        .find(|(kind, _)| *kind == scope)
        .map_or_else(|| scope.to_owned(), |(_, label)| (*label).to_owned())
}

/// A path as the `--paths` mode shows it.
pub(crate) fn display_path(value: Option<&str>, mode: &str) -> String {
    let Some(value) = value else {
        return NONE_TEXT.to_owned();
    };
    if mode == PATH_NONE {
        return "(hidden)".to_owned();
    }
    if mode == PATH_COMPACT {
        return posix_name(value).to_owned();
    }
    value.to_owned()
}

/// `PurePosixPath(value).name`.
fn posix_name(value: &str) -> &str {
    let trimmed: &str = value.trim_end_matches('/');
    let name: &str = trimmed.rsplit('/').next().unwrap_or(trimmed);
    if name == CURRENT_DIRECTORY { "" } else { name }
}

/// `(<count>)`, or `(<returned> of <total>[, <n> collapsed])` for a paged section.
pub(crate) fn section_count(section: Option<&ScopeSection>, count: usize) -> String {
    let Some(section) = section else {
        return format!("({count})");
    };
    let suffix: String = if section.collapsed_count == 0 {
        String::new()
    } else {
        format!(", {} collapsed", section.collapsed_count)
    };
    format!("({} of {}{suffix})", section.returned, section.total)
}

/// `count singular`, or the plural when the count is not one.
pub(crate) fn count_noun(count: i64, singular: &str, plural: &str) -> String {
    format!("{count} {}", if count == 1 { singular } else { plural })
}

pub(crate) fn completeness_line(style: CliStyle, complete: bool) -> String {
    let state: String = if complete {
        style.success("complete")
    } else {
        style.warning("partial")
    };
    format!("{} {state}", style.muted("Completeness:"))
}

fn diagnostic_facts(diagnostics: &[ReportDiagnostic]) -> Vec<&DiagnosticFacts> {
    diagnostics
        .iter()
        .filter_map(|diagnostic| match diagnostic {
            ReportDiagnostic::Raised(facts) => Some(facts),
            ReportDiagnostic::Index(_) => None,
        })
        .collect()
}

/// Whether any diagnostic is an error.
pub(crate) fn has_error(diagnostics: &[ReportDiagnostic]) -> bool {
    diagnostic_facts(diagnostics)
        .iter()
        .any(|facts| facts.severity == ERROR_SEVERITY)
}

/// The diagnostics section; empty unless there are diagnostics or the output is verbose.
pub(crate) fn diagnostic_lines(
    style: CliStyle,
    diagnostics: &[ReportDiagnostic],
    verbose: bool,
) -> Vec<String> {
    let facts: Vec<&DiagnosticFacts> = diagnostic_facts(diagnostics);
    if facts.is_empty() && !verbose {
        return Vec::new();
    }
    let count: String = format!("({})", facts.len());
    let mut lines: Vec<String> = vec![if facts.is_empty() {
        plain_header(style, "Diagnostics", &count)
    } else {
        header(
            "Diagnostics",
            &count,
            (&|text: &str| style.error_strong(text), &|text: &str| {
                style.error(text)
            }),
        )
    }];
    if facts.is_empty() {
        lines.push(none_line(style));
    }
    for diagnostic in facts {
        let severity: String = diagnostic.severity.to_uppercase();
        let severity_text: String = if diagnostic.severity == ERROR_SEVERITY {
            style.error_strong(&severity)
        } else {
            style.warning_strong(&severity)
        };
        let location: String = diagnostic
            .path
            .as_ref()
            .map(|path| format!(" {}", style.muted(path)))
            .unwrap_or_default();
        lines.push(format!(
            "  {severity_text} {}{location}: {}",
            diagnostic.code, diagnostic.message
        ));
    }
    lines
}

/// What a follow-up command adds to the request's own options.
#[derive(Clone, Copy, Default)]
pub(crate) struct FollowUp<'a> {
    pub(crate) browse: Option<&'a str>,
    pub(crate) list_path: Option<&'a str>,
    pub(crate) after: Option<&'a str>,
    pub(crate) globals_all: bool,
}

fn option(name: &str, value: &str) -> [String; 2] {
    [name.to_owned(), value.to_owned()]
}

/// The `sqb scope` command that repeats this request with `extra`, shell-quoted.
pub(crate) fn follow_up(request: &ScopeTextRequest, extra: FollowUp<'_>) -> String {
    let mut args: Vec<String> = vec!["sqb".to_owned(), "scope".to_owned()];
    match &request.target {
        Some(target) => args.push(target.clone()),
        None => args.extend(option("--at", request.at.as_deref().unwrap_or_default())),
    }
    if let Some(browse) = extra.browse {
        args.extend(option("--browse", browse));
    }
    if let Some(list_path) = extra.list_path {
        args.extend(option("--list", list_path));
    }
    if let Some(defined_under) = &request.defined_under {
        args.extend(option("--defined-under", defined_under));
    }
    for kind in &request.kinds {
        args.extend(option("--kind", kind));
    }
    if let Some(glob) = &request.glob {
        args.extend(option("--match", glob));
    }
    if request.used_only {
        args.push("--used-only".to_owned());
    }
    if extra.globals_all {
        if let Some(as_path) = &request.as_path {
            args.extend(option("--as-path", as_path));
        }
        if request.include_nearby {
            args.push("--include-nearby".to_owned());
        }
        if request.nearby_depth != 1 {
            args.extend(option("--nearby-depth", &request.nearby_depth.to_string()));
        }
        if request.dependency_depth != 0 {
            args.extend(option(
                "--dependency-depth",
                &request.dependency_depth.to_string(),
            ));
        }
        if let Some(explain) = &request.explain {
            args.extend(option("--explain", explain));
        }
    }
    if request.page_size != DEFAULT_PAGE_SIZE {
        args.extend(option("--page-size", &request.page_size.to_string()));
    }
    if let Some(after) = extra.after {
        args.extend(option("--after", after));
    }
    if extra.globals_all {
        args.extend(option("--globals", GLOBAL_ALL));
    } else if request.globals != GLOBAL_SUMMARY {
        args.extend(option("--globals", &request.globals));
    }
    if request.paths != PATH_RELATIVE {
        args.extend(option("--paths", &request.paths));
    }
    if request.verbose {
        args.push("--verbose".to_owned());
    }
    if request.no_cache {
        args.push("--no-cache".to_owned());
    }
    args.iter()
        .map(|arg| shell_quote(arg))
        .collect::<Vec<String>>()
        .join(" ")
}
