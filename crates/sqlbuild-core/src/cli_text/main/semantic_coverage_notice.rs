//! One actionable notice summarizing partial semantic checks, without counting as a warning.

use std::collections::BTreeMap;

use crate::cli_text::constants::{
    DEFAULT_ACTION, INVALID_UPSTREAM, NOTICE_DISPLAY_LIMIT, OPEN_INPUT, OPEN_SOURCE,
};

/// The action that clears one partial-check reason.
fn action(reason: &str) -> String {
    if let Some(source) = reason.strip_prefix(OPEN_SOURCE) {
        return format!(
            "run `sqb contract generate --from <target> --select source:{source} --write` and \
             enforce the complete source contract"
        );
    }
    if reason.starts_with(INVALID_UPSTREAM) {
        return "fix the upstream error, then run `sqb compile --no-cache`".to_owned();
    }
    match reason {
        "some output types are unknown" => {
            "declare output types, then run `sqb compile --no-cache`"
        }
        "output shape could not be inferred" => {
            "declare the output schema; run `sqb compile --no-cache`"
        }
        "unresolved star over open inputs" => {
            "declare complete input contracts, then run `sqb compile --no-cache`"
        }
        "SQL analysis disabled" => "enable sql_analysis, then run `sqb compile --no-cache`",
        "type checking awaits dialect coercion support" => {
            "use a supported dialect for type checks; run `sqb compile --json` to inspect coverage"
        }
        _ => DEFAULT_ACTION,
    }
    .to_owned()
}

/// The notice for each model's partial-check reasons, or `None` when every check was complete.
#[must_use]
pub fn semantic_coverage_notice(reasons: &[(String, Vec<String>)]) -> Option<String> {
    if reasons.is_empty() {
        return None;
    }
    let mut by_model: Vec<&(String, Vec<String>)> = reasons.iter().collect();
    by_model.sort_by(|left, right| left.0.cmp(&right.0));
    let mut groups: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    for (model, values) in by_model {
        for reason in values {
            groups
                .entry(reason.as_str())
                .or_default()
                .push(model.as_str());
        }
    }
    let mut lines: Vec<String> = vec![format!(
        "Semantic checks were partial for {} models:",
        reasons.len()
    )];
    for (reason, models) in groups.iter().take(NOTICE_DISPLAY_LIMIT) {
        let suffix: String = if models.len() > NOTICE_DISPLAY_LIMIT {
            format!(", and {} more", models.len() - NOTICE_DISPLAY_LIMIT)
        } else {
            String::new()
        };
        let detail: String = reason
            .replace(OPEN_SOURCE, "reads open source ")
            .replace(OPEN_INPUT, "reads open input ");
        let shown: Vec<&str> = models.iter().take(NOTICE_DISPLAY_LIMIT).copied().collect();
        lines.push(format!(
            "  {}{suffix}: {detail}; {}.",
            shown.join(", "),
            action(reason)
        ));
    }
    if groups.len() > NOTICE_DISPLAY_LIMIT {
        lines.push(format!(
            "  and {} more reasons; run `sqb compile --json` for the full model/reason list.",
            groups.len() - NOTICE_DISPLAY_LIMIT
        ));
    }
    Some(lines.join("\n"))
}
