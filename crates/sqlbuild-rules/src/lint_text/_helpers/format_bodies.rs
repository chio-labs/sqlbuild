//! Body preparation, request building and result splicing for SQL body formatting.

use std::collections::{BTreeMap, HashMap};
use std::sync::LazyLock;

use regex::Regex;
use sqlbuild_attachments::ceremonial_select::main::omitted_select_offset::omitted_select_offset;
use sqlbuild_attachments::ceremonial_select::models::OmittedSelect;
use sqlbuild_core::text::main::python_isspace::python_isspace;
use sqlbuild_core::text::main::python_splitlines::python_splitlines;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::dsl_headers::main::measurement_body_ranges::measurement_body_ranges;
use crate::dsl_headers::main::scan_headers::scan_headers;
use crate::dsl_headers::main::sql_body_ranges::sql_body_ranges;
use crate::dsl_headers::models::HeaderSpan;
use crate::lint_text::_helpers::sites::compiled;
use crate::lint_text::constants::{
    DECLARATION_GROUP_DIRECTORY, DECLINED_WITHOUT_REASON, FIXTURE_HEADER_KINDS, FORMAT_API_VERSION,
    GLOBAL_NAMED_ROOTS, GROUPED_NAMED_ROLES, LINE_COMMENT_PREFIX, MAX_FUNCTION_CALL_DEPTH,
    MOVED_OMITTED_SELECT, OMITTED_CEREMONIAL_SELECT_SQL, OMITTED_SELECT_SUFFIX_PATTERN,
};
use crate::lint_text::errors::LintTextError;
use crate::lint_text::main::neutralize_interpolation::neutralize_interpolation;
use crate::lint_text::main::restore_interpolation::restore_interpolation;
use crate::lint_text::models::{FormatFault, FormatFile, InterpolationSite, PreparedBody};
use crate::sql_lint::models::{FormatRequest, FormatResponse};

static OMITTED_SELECT_SUFFIX: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| Regex::new(OMITTED_SELECT_SUFFIX_PATTERN));

/// Deduplicated format requests, keyed by neutralized SQL and sentinel widths.
#[derive(Default)]
pub(crate) struct RequestTable {
    pub(crate) requests: Vec<FormatRequest>,
    index: HashMap<(String, Vec<(String, usize)>), usize>,
}

impl RequestTable {
    pub(crate) fn insert(
        &mut self,
        sql: String,
        widths: BTreeMap<String, usize>,
        options: (&str, usize),
    ) -> usize {
        let key: (String, Vec<(String, usize)>) = (
            sql.clone(),
            widths
                .iter()
                .map(|(name, width)| (name.clone(), *width))
                .collect(),
        );
        if let Some(index) = self.index.get(&key) {
            return *index;
        }
        self.requests.push(FormatRequest {
            version: FORMAT_API_VERSION,
            sql,
            dialect: options.0.to_string(),
            max_function_call_depth: Some(MAX_FUNCTION_CALL_DEPTH),
            line_width: Some(options.1),
            token_widths: widths.into_iter().collect(),
        });
        let _ = self.index.insert(key, self.requests.len() - 1);
        self.requests.len() - 1
    }
}

/// Whether a project-relative path lies in a generic or singular audit role.
fn is_audit_path(parts: &[String]) -> bool {
    let directories: &[String] = &parts[..parts.len().saturating_sub(1)];
    for (root, audit) in GLOBAL_NAMED_ROOTS {
        if starts_with(directories, root) {
            return audit;
        }
    }
    for (index, part) in directories.iter().enumerate() {
        if part != DECLARATION_GROUP_DIRECTORY {
            continue;
        }
        for (role, audit) in GROUPED_NAMED_ROLES {
            if starts_with(&directories[index + 1..], role) {
                return audit;
            }
        }
    }
    false
}

fn starts_with(parts: &[String], prefix: &[&str]) -> bool {
    parts.len() >= prefix.len() && parts.iter().zip(prefix).all(|(part, name)| part == name)
}

/// The lintable body ranges of one file, measurement blocks first for audits.
fn body_ranges(file: &FormatFile, text: &[char], headers: &[HeaderSpan]) -> Vec<(usize, usize)> {
    if file.relative_parts.as_deref().is_some_and(is_audit_path) {
        let ranges: Vec<(usize, usize)> = measurement_body_ranges(text);
        if !ranges.is_empty() {
            return ranges;
        }
    }
    sql_body_ranges(text, headers)
}

/// One prepared body with its neutralized SQL and sentinel widths, awaiting its request index.
pub(crate) type PendingBody = (PreparedBody, String, BTreeMap<String, usize>);

/// Prepare every body of one file for formatting.
pub(crate) fn prepare_file(
    file: &FormatFile,
    dialect: &str,
) -> Result<Vec<PendingBody>, LintTextError> {
    let text: Vec<char> = file.contents.chars().collect();
    let headers: Vec<HeaderSpan> = scan_headers(&text, false);
    let omits: bool = headers
        .iter()
        .any(|header| FIXTURE_HEADER_KINDS.contains(&header.kind.as_str()));
    let syntax: LexicalSyntax = LexicalSyntax {
        line_comment_prefixes: vec![LINE_COMMENT_PREFIX.to_string()],
        ..LexicalSyntax::default()
    };
    let mut prepared: Vec<PendingBody> = Vec::new();
    for (start, end) in body_ranges(file, &text, &headers) {
        let body: &[char] = &text[start..end];
        let core_end: usize = body
            .iter()
            .rposition(|character| !python_isspace(*character))
            .map_or(0, |index| index + 1);
        let mut core: String = body[..core_end].iter().collect();
        let mut trailing: String = body[core_end..].iter().collect();
        let omitted: Option<usize> = if omits {
            match omitted_select_offset(&core, &syntax) {
                OmittedSelect::At(offset) => Some(offset),
                OmittedSelect::Absent => None,
            }
        } else {
            None
        };
        if let Some(offset) = omitted {
            let characters: Vec<char> = core.chars().collect();
            trailing = characters[offset..].iter().collect::<String>() + &trailing;
            core = characters[..offset].iter().collect();
        }
        let neutralized = neutralize_interpolation(&core, dialect, true)?;
        let mut sql: String = neutralized.text;
        if omitted.is_some() {
            sql.push_str(OMITTED_CEREMONIAL_SELECT_SQL);
        }
        let widths: BTreeMap<String, usize> = sentinel_widths(&neutralized.sites);
        let body: PreparedBody = PreparedBody {
            start,
            end,
            trailing,
            request: 0,
            sites: neutralized.sites,
            omits_select: omitted.is_some(),
        };
        prepared.push((body, sql, widths));
    }
    Ok(prepared)
}

/// The printed width of the SQLBuild syntax each sentinel stands in for, where it differs.
fn sentinel_widths(sites: &[InterpolationSite]) -> BTreeMap<String, usize> {
    sites
        .iter()
        .filter(|site| {
            site.original_text.chars().count() != site.sentinel.chars().count()
                || site.original_text.contains('\n')
        })
        .map(|site| {
            (
                site.sentinel.to_uppercase(),
                printed_width(&site.original_text),
            )
        })
        .collect()
}

/// The widest line of `text`, in characters.
fn printed_width(text: &str) -> usize {
    let lines: Vec<&str> = python_splitlines(text);
    lines
        .iter()
        .map(|line| line.chars().count())
        .max()
        .unwrap_or(0)
}

/// The formatted text replacing one body, or why the body was left unchanged.
pub(crate) fn formatted_body(
    prepared: &PreparedBody,
    response: &FormatResponse,
) -> Result<Option<String>, String> {
    if !response.formatted {
        return Err(response
            .reason
            .clone()
            .filter(|reason| !reason.is_empty())
            .unwrap_or_else(|| DECLINED_WITHOUT_REASON.to_string()));
    }
    let mut sql: &str = &response.sql;
    let mut changed: bool = response.changed;
    if prepared.omits_select {
        let pattern: &Regex =
            compiled(&OMITTED_SELECT_SUFFIX).map_err(|error| error.to_string())?;
        let Some(suffix) = pattern.find(sql) else {
            return Err(MOVED_OMITTED_SELECT.to_string());
        };
        sql = &sql[..suffix.start()];
        changed = true;
    }
    if !changed {
        return Ok(None);
    }
    restore_interpolation(sql, &prepared.sites)
        .map(|restored| Some(restored + &prepared.trailing))
        .map_err(|error| error.to_string())
}

/// One file's text with every formatted body spliced in, if it changed, and its declined bodies.
pub(crate) fn splice_file(
    index: usize,
    contents: &str,
    bodies: &[PreparedBody],
    responses: &[FormatResponse],
) -> (Option<String>, Vec<FormatFault>) {
    let original: Vec<char> = contents.chars().collect();
    let mut updated: Vec<char> = original.clone();
    let mut faults: Vec<FormatFault> = Vec::new();
    for body in bodies.iter().rev() {
        match formatted_body(body, &responses[body.request]) {
            Ok(Some(replacement)) => {
                let _ = updated.splice(body.start..body.end, replacement.chars());
            }
            Ok(None) => {}
            Err(reason) => faults.push(FormatFault {
                file: index,
                line: original[..body.start]
                    .iter()
                    .filter(|character| **character == '\n')
                    .count()
                    + 1,
                reason,
            }),
        }
    }
    let formatted: Option<String> = (updated != original).then(|| updated.into_iter().collect());
    (formatted, faults)
}
