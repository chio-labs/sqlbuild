//! Python's `unneeded_opt_out_diagnostic` text for a rejected model opt-out.

use std::sync::LazyLock;

use regex::Regex;

use crate::semantic_checks::_helpers::explanation::messages::{compiled, pattern};
use crate::semantic_checks::constants::{
    ADDITIONAL_HELP_SEPARATOR, FINDING_KINDS, PROJECT_CONFIG_FILENAME, REQUIRE_SQL_ANALYSIS_KEY,
    SETTING_SNIPPET_INDENT, SETTINGS_SECTION,
};
use crate::semantic_checks::models::{OptOutDiagnostic, SemanticFailure};

static FINDING_PATTERNS: LazyLock<Result<Regex, String>> = LazyLock::new(|| {
    let alternatives: Vec<String> = FINDING_KINDS
        .iter()
        .map(|(code, _, _)| format!("({code})"))
        .collect();
    compiled(&alternatives.join("|"))
});

/// One P009 error for a model's rejected `sql_analysis false`, counting the findings it hid.
pub(crate) fn opt_out_diagnostic(
    model: usize,
    name: &str,
    location_file: Option<&str>,
    hidden_codes: &[&str],
) -> Result<OptOutDiagnostic, SemanticFailure> {
    let findings: String = finding_counts(pattern(&FINDING_PATTERNS)?, hidden_codes);
    let opt_out: &str = if location_file == Some(PROJECT_CONFIG_FILENAME) {
        "`sql_analysis = false` from this [path_defaults] entry"
    } else {
        "`sql_analysis false`"
    };
    let fix: String = if findings.is_empty() {
        format!("remove {opt_out}; it is not hiding any findings")
    } else {
        format!(
            "remove {opt_out} and fix the findings it was hiding: {findings} \
             (run `sqb compile` to see them)"
        )
    };
    let setting_help: String = format!(
        "to allow `sql_analysis false` on any model, SQL test or audit, set this in \
         {PROJECT_CONFIG_FILENAME}:\n{SETTING_SNIPPET_INDENT}[{SETTINGS_SECTION}]\n\
         {SETTING_SNIPPET_INDENT}{REQUIRE_SQL_ANALYSIS_KEY} = false"
    );
    Ok(OptOutDiagnostic {
        model,
        message: format!("`sql_analysis false` is not needed for model '{name}'"),
        note: format!(
            "{PROJECT_CONFIG_FILENAME} sets [{SETTINGS_SECTION}] {REQUIRE_SQL_ANALYSIS_KEY} = true\
             , which only allows `sql_analysis false` on SQL that SQLBuild cannot parse; \
             this model parses successfully."
        ),
        help: format!("{fix}{ADDITIONAL_HELP_SEPARATOR}{setting_help}"),
    })
}

/// Python's `_finding_counts`: kinds by descending count, ties in first-seen order.
fn finding_counts(kinds: &Regex, codes: &[&str]) -> String {
    let mut counts: Vec<((&str, &str), usize)> = Vec::new();
    for code in codes {
        let kind = finding_kind(kinds, code);
        match counts.iter_mut().find(|(existing, _)| *existing == kind) {
            Some((_, count)) => *count += 1,
            None => counts.push((kind, 1)),
        }
    }
    counts.sort_by_key(|(_, count)| std::cmp::Reverse(*count));
    let mut rendered: Vec<String> = Vec::with_capacity(counts.len());
    for ((singular, plural), count) in counts {
        let noun = if count == 1 { singular } else { plural };
        rendered.push(format!("{count} {noun}"));
    }
    rendered.join(", ")
}

/// Python's `_finding_kind`: the first pattern matching `code`, as one alternation group.
fn finding_kind(kinds: &Regex, code: &str) -> (&'static str, &'static str) {
    let Some(captures) = kinds.captures(code) else {
        return ("other finding", "other findings");
    };
    for (index, (_, singular, plural)) in FINDING_KINDS.iter().enumerate() {
        if captures.get(index + 1).is_some() {
            return (singular, plural);
        }
    }
    ("other finding", "other findings")
}
