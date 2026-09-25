//! One native lexical pass for interpolation provenance and CTE dependency evidence.

use std::collections::HashSet;
use std::sync::LazyLock;

use regex::Regex;

use crate::rules::main::quote_policy::quote_policy;
use crate::sql_lint::types::{InterpolationSite, PreparedSql};
use crate::sql_scan::main::matching_paren::matching_paren as scan_matching_paren;
use crate::sql_scan::models::QuotePolicy;

const SITE_PATTERN: &str =
    r#"(?P<site>@@|\$\{|@|(?:__dbt_ref|__ref|__seed|__source|__table_fn|__udf)\s*\()"#;
const NON_CODE_PATTERN: &str = r#"--[^\n]*(?:\n|\z)|/\*[\s\S]*?(?:\*/|\z)|'(?:\\.|''|[^'\\])*(?:'|\z)|"(?:\\.|""|[^"\\])*(?:"|\z)"#;
const BACKTICK_PATTERN: &str = r#"`(?:``|[^`])*(?:`|\z)"#;

static SITES: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| Regex::new(&format!("{NON_CODE_PATTERN}|{SITE_PATTERN}")));
static BACKTICK_SITES: LazyLock<Result<Regex, regex::Error>> = LazyLock::new(|| {
    Regex::new(&format!(
        "{NON_CODE_PATTERN}|{BACKTICK_PATTERN}|{SITE_PATTERN}"
    ))
});
static CTES: LazyLock<Result<Regex, regex::Error>> = LazyLock::new(|| {
    Regex::new(
        r#"(?is)(?:\bWITH(?:\s+RECURSIVE)?|,)\s*["`\[]?(?P<name>[A-Za-z_][A-Za-z0-9_]*)["`\]]?(?:\s*\([^)]*\))?\s+AS\s*\("#,
    )
});
static WORDS: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| Regex::new(r"\b[A-Za-z_][A-Za-z0-9_]*\b"));
static OPAQUE_CTE: LazyLock<Result<Regex, regex::Error>> =
    LazyLock::new(|| Regex::new(r"(?i)\b[A-Za-z_][A-Za-z0-9_]*\s+AS\s*\(\s*(?:--[^\n]*\n\s*)?$"));

/// Return whether SQL lint treats backticks as identifier quotes for `dialect`, as rules do.
pub(crate) fn backtick_identifiers(dialect: &str) -> bool {
    quote_policy(dialect).backtick_identifiers
}

pub(crate) fn prepare(
    expanded: &str,
    before_expansion: &str,
    prior_sites: &[usize],
    dialect: &str,
) -> Result<Option<PreparedSql>, String> {
    if !expanded.is_ascii() || !before_expansion.is_ascii() {
        return Ok(None);
    }
    let policy = QuotePolicy::SQL_LINT.with_backtick_identifiers(backtick_identifiers(dialect));
    let sites_regex = if policy.backtick_identifiers {
        &BACKTICK_SITES
    } else {
        &SITES
    };
    let site_pattern = sites_regex.as_ref().map_err(|error| error.to_string())?;
    let cte_pattern = CTES.as_ref().map_err(|error| error.to_string())?;
    let word_pattern = WORDS.as_ref().map_err(|error| error.to_string())?;
    let opaque_pattern = OPAQUE_CTE.as_ref().map_err(|error| error.to_string())?;
    let mut text = String::with_capacity(expanded.len());
    let mut sites: Vec<InterpolationSite> = Vec::new();
    let mut copied_to = 0;
    for captures in site_pattern.captures_iter(expanded) {
        let Some(site) = captures.name("site") else {
            continue;
        };
        let start = site.start();
        if start < copied_to {
            continue;
        }
        let Some(end) = site_end(expanded, start, policy) else {
            continue;
        };
        text.push_str(&expanded[copied_to..start]);
        let sentinel = format!("__sqb_lint_{}__", sites.len());
        let output_start = text.len();
        text.push_str(&sentinel);
        sites.push((
            sentinel,
            output_start,
            text.len(),
            start,
            end,
            expanded[start..end].to_string(),
        ));
        copied_to = end;
    }
    text.push_str(&expanded[copied_to..]);
    let names: HashSet<String> = cte_pattern
        .captures_iter(expanded)
        .map(|capture| capture["name"].to_ascii_lowercase())
        .collect();
    let mut referenced: HashSet<String> = HashSet::new();
    for site in &sites {
        referenced.extend(
            word_pattern
                .find_iter(&site.5)
                .map(|word| word.as_str().to_ascii_lowercase())
                .filter(|word| names.contains(word)),
        );
    }
    for &start in prior_sites {
        let Some(prefix) = before_expansion.get(..start) else {
            return Ok(None);
        };
        if opaque_pattern.is_match(prefix) {
            referenced.extend(
                cte_pattern
                    .captures_iter(prefix)
                    .map(|capture| capture["name"].to_ascii_lowercase())
                    .filter(|name| names.contains(name)),
            );
        }
    }
    let mut referenced: Vec<String> = referenced.into_iter().collect();
    referenced.sort();
    Ok(Some((text, sites, referenced)))
}

fn site_end(text: &str, start: usize, policy: QuotePolicy) -> Option<usize> {
    let bytes = text.as_bytes();
    match bytes[start] {
        b'@' if bytes.get(start + 1) == Some(&b'@') => Some(scan_name(bytes, start + 2, true)),
        b'@' if bytes.get(start + 1) == Some(&b'\'') => {
            text[start + 2..].find('\'').map(|index| start + index + 3)
        }
        b'@' => {
            let first = *bytes.get(start + 1)?;
            if !first.is_ascii_alphabetic() && first != b'_' {
                return None;
            }
            let end = scan_name(bytes, start + 1, false);
            if bytes.get(end) == Some(&b'(') {
                matching_paren(bytes, end, policy)
            } else {
                Some(end)
            }
        }
        b'$' => text[start + 2..].find('}').map(|index| start + index + 3),
        b'_' => {
            let end = scan_name(bytes, start, false);
            (bytes.get(end) == Some(&b'('))
                .then(|| matching_paren(bytes, end, policy))
                .flatten()
        }
        _ => None,
    }
}

fn scan_name(bytes: &[u8], mut index: usize, interpolation: bool) -> usize {
    while bytes.get(index).is_some_and(|byte| {
        byte.is_ascii_alphanumeric()
            || *byte == b'_'
            || interpolation && matches!(byte, b':' | b'.')
    }) {
        index += 1;
    }
    index
}

fn matching_paren(bytes: &[u8], open: usize, policy: QuotePolicy) -> Option<usize> {
    match scan_matching_paren(bytes, open, policy) {
        Ok(close) => Some(close + 1),
        Err(_) => None,
    }
}
