//! The C270 report of a default full diff stopped by table sizes.

use sqlbuild_core::json::models::JsonValue;

use crate::diff_report::_helpers::payload::{object, text};
use crate::diff_report::_helpers::size_guard::{command, scope_arguments, side_payload, side_text};
use crate::diff_report::constants::BOUNDED_WINDOW_PLACEHOLDER;
use crate::diff_report::models::{DiffRequestFacts, FullDiffModelFacts, SizeGuardReport};

/// Every blocked model, the explicit replacement commands, and how to raise the limits.
#[must_use]
pub fn size_guard_report(
    request: &DiffRequestFacts,
    (from_target, to_target): (&str, &str),
    guard_message: &str,
    blocked: &[FullDiffModelFacts],
) -> SizeGuardReport {
    let scope: Vec<String> = scope_arguments(request);
    let mut prefix: Vec<String> = vec!["sqb".to_owned()];
    if let Some(project_dir) = &request.project_dir {
        prefix.extend(["--project-dir".to_owned(), project_dir.clone()]);
    }
    prefix.extend(["diff".to_owned(), format!("{from_target}:{to_target}")]);
    let full: String = command(&prefix, &["--full"], &scope);
    let bounded: Option<String> = blocked
        .iter()
        .all(|model| model.has_cursor)
        .then(|| command(&prefix, &["--bounded", BOUNDED_WINDOW_PLACEHOLDER], &scope));
    let schema_only: String = command(&prefix, &["--schema-only"], &scope);
    let mut lines: Vec<String> = vec![guard_message.to_owned()];
    for model in blocked {
        lines.push(format!(
            "  {}: {}; {}{}",
            model.name,
            side_text(&model.left),
            side_text(&model.right),
            if model.has_cursor { "" } else { "; no cursor" }
        ));
    }
    lines.push("Run one of these instead:".to_owned());
    lines.push(format!("  {full}"));
    if let Some(bounded) = &bounded {
        lines.push(format!("  {bounded}"));
    }
    lines.push(format!("  {schema_only}"));
    let mut over_targets: Vec<&str> = Vec::new();
    for side in blocked.iter().flat_map(|model| [&model.left, &model.right]) {
        if side.exceeds_limit && !over_targets.contains(&side.target.as_str()) {
            over_targets.push(&side.target);
        }
    }
    let bounded_help: String = if bounded.is_some() {
        format!(
            ", --bounded compares a recent cursor window (replace {BOUNDED_WINDOW_PLACEHOLDER} with a duration such as 7d)"
        )
    } else {
        String::new()
    };
    let raise: Vec<String> = over_targets
        .iter()
        .map(|target| format!("targets.{target}.diff.max_full_rows"))
        .collect();
    let models: Vec<JsonValue> = blocked
        .iter()
        .map(|model| {
            object(vec![
                ("name", text(&model.name)),
                ("has_cursor", JsonValue::Bool(model.has_cursor)),
                ("from", side_payload(&model.left)),
                ("to", side_payload(&model.right)),
            ])
        })
        .collect();
    SizeGuardReport {
        message: lines.join("\n"),
        help: format!(
            "--full compares every row{bounded_help}, and --schema-only compares columns only; or raise {}",
            raise.join(" and ")
        ),
        details: object(vec![
            ("from_target", text(from_target)),
            ("to_target", text(to_target)),
            ("models", JsonValue::Array(models)),
            (
                "commands",
                object(vec![
                    ("full", text(&full)),
                    ("bounded", bounded.as_deref().map_or(JsonValue::Null, text)),
                    ("schema_only", text(&schema_only)),
                ]),
            ),
        ]),
    }
}
