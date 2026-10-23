//! Sections of the janitor plan preview.

use crate::cli_text::models::CliStyle;
use crate::janitor_text::_helpers::usage::{
    checked_usage, in_use_candidates, usage_detail, usage_notices,
};
use crate::janitor_text::constants::{
    DROP_EARLY, DROP_EXPIRED, DROP_MISSING, LABEL_WIDTH, TREE_BLANK, TREE_BRANCH_GLYPH,
    TREE_CONTINUATION, TREE_LAST_GLYPH, VERBOSE_FLAG,
};
use crate::janitor_text::models::{ArchiveCandidateText, JanitorPlanText, OldNameViewText};

/// The first `limit` items, or all of them, and how many are hidden.
fn visible<T>(items: &[T], limit: Option<usize>) -> (&[T], usize) {
    let shown: usize = limit.map_or(items.len(), |limit| items.len().min(limit));
    (&items[..shown], items.len() - shown)
}

/// The dim `... and N more` line of a section that hides entries.
fn overflow(style: CliStyle, hidden: usize, indent: &str) -> String {
    if hidden == 0 {
        return String::new();
    }
    format!(
        "{}\n",
        style.muted(&format!(
            "{indent}... and {hidden} more (use {VERBOSE_FLAG} to show all)"
        ))
    )
}

fn row(label: &str, rendered: &str) -> String {
    format!("  {label:<LABEL_WIDTH$} {rendered}\n")
}

fn count_row<T>(style: CliStyle, label: &str, items: &[T]) -> String {
    let count: String = items.len().to_string();
    let rendered: String = if items.is_empty() {
        style.accent(&count)
    } else {
        style.warning(&count)
    };
    row(label, &rendered)
}

fn tree_connector(style: CliStyle, last: bool) -> String {
    style.muted(if last {
        TREE_LAST_GLYPH
    } else {
        TREE_BRANCH_GLYPH
    })
}

/// `age Nd`, or `age unknown`.
fn age(days: Option<i64>) -> String {
    days.map_or_else(
        || "age unknown".to_owned(),
        |days| format!("age {}d", days.max(0)),
    )
}

/// The retention, schema and per-action counts.
pub(crate) fn summary(plan: &JanitorPlanText, style: CliStyle) -> String {
    let mut text: String = String::new();
    if plan.retention_days == 0 {
        text.push_str(&row("retention", &style.accent("disabled (0 days)")));
        text.push_str(&row("age metadata", &style.accent("not checked")));
    } else {
        text.push_str(&row(
            "retention",
            &style.accent(&format!("{} days", plan.retention_days)),
        ));
        if !plan.age_metadata_supported {
            text.push_str(&row("age metadata", &style.accent("unavailable")));
        }
    }
    if plan.direct_mode {
        text.push_str(&row(
            "archive retention",
            &style.accent(&format!("{} days", plan.archive_retention_days)),
        ));
    }
    text.push_str(&row(
        "schemas scanned",
        &style.accent(&plan.scanned_schema_count.to_string()),
    ));
    text.push_str(&row(
        "schemas skipped",
        &style.accent(&plan.skipped_schemas.len().to_string()),
    ));
    if plan.direct_mode {
        text.push_str(&count_row(
            style,
            "relations to archive",
            &plan.archive_candidates,
        ));
        if let Some(check) = checked_usage(plan) {
            if check.keep_in_use {
                text.push_str(&count_row(style, "kept (in use)", &plan.kept_in_use));
            } else {
                text.push_str(&count_row(style, "in use", &in_use_candidates(plan)));
            }
        }
        text.push_str(&count_row(
            style,
            "archives to delete",
            &plan.archive_deletions,
        ));
        text.push_str(&row(
            "archives retained",
            &style.accent(&plan.retained_archives.len().to_string()),
        ));
        text.push_str(&row(
            "old name views",
            &style.accent(&plan.old_name_live.len().to_string()),
        ));
        text.push_str(&count_row(
            style,
            "old name views to drop",
            &plan.old_name_drops,
        ));
    } else {
        text.push_str(&count_row(style, "eligible for deletion", &plan.candidates));
    }
    text.push_str(&count_row(style, "query artifacts", &plan.query_artifacts));
    text.push_str(&count_row(style, "review schemas", &plan.review_schemas));
    text.push_str(&count_row(style, "direct state pruned", &plan.state_prunes));
    text.push_str(&row(
        "objects skipped",
        &style.accent(&plan.skipped_relations.len().to_string()),
    ));
    let notices: Vec<String> = usage_notices(plan);
    if !notices.is_empty() {
        text.push('\n');
        for notice in notices {
            text.push_str(&format!("  {}\n", style.warning(&notice)));
        }
    }
    text
}

/// In-use archive candidates with their readers, or the in-use relations kept instead.
fn in_use(plan: &JanitorPlanText, limit: Option<usize>, style: CliStyle) -> String {
    let Some(check) = checked_usage(plan) else {
        return String::new();
    };
    let (title, candidates): (&str, Vec<&ArchiveCandidateText>) = if check.keep_in_use {
        ("Kept (in use)", plan.kept_in_use.iter().collect())
    } else {
        ("In use", in_use_candidates(plan))
    };
    let lines: Vec<(String, Option<String>)> = candidates
        .into_iter()
        .map(|candidate| {
            (
                candidate.name.clone(),
                usage_detail(candidate, &check.window),
            )
        })
        .collect();
    listing((style, limit), title, &lines)
}

/// Schemas whose active sources block every janitor action.
pub(crate) fn blocked(plan: &JanitorPlanText, limit: Option<usize>, style: CliStyle) -> String {
    if plan.blocked_schemas.is_empty() {
        return String::new();
    }
    let action: &str = if plan.direct_mode {
        "archive"
    } else {
        "deletion"
    };
    let mut text: String = format!(
        "\n{}\n  {}\n",
        style.error_strong("Janitor blocked"),
        style.error("Managed target schemas contain active configured sources.")
    );
    for schema in &plan.blocked_schemas {
        text.push_str(&format!(
            "  {}  {}\n",
            style.object_name(&schema.name),
            style.error_muted(&format!(
                "active sources: {}",
                schema.source_names.join(", ")
            ))
        ));
        let (candidates, hidden) = visible(&schema.suppressed_candidates, limit);
        for name in candidates {
            text.push_str(&format!(
                "    {}\n",
                style.error_muted(&format!("suppressed {action}: {name}"))
            ));
        }
        text.push_str(&overflow(style, hidden, "    "));
        let (deletions, hidden) = visible(&schema.suppressed_archive_deletions, limit);
        for name in deletions {
            text.push_str(&format!(
                "    {}\n",
                style.error_muted(&format!("suppressed archive deletion: {name}"))
            ));
        }
        text.push_str(&overflow(style, hidden, "    "));
    }
    text.push_str(&format!(
        "  {}\n",
        style.error("No janitor actions will be performed.")
    ));
    text
}

/// Relations to archive, archives to delete, and retained archives.
pub(crate) fn archives(plan: &JanitorPlanText, limit: Option<usize>, style: CliStyle) -> String {
    let mut text: String = String::new();
    if !plan.archive_candidates.is_empty() {
        text.push_str(&format!("\n{}\n", style.success("Relations to archive")));
        let (candidates, hidden) = visible(&plan.archive_candidates, limit);
        for candidate in candidates {
            let expiry: String = if candidate.expires_now {
                "deleted in this run".to_owned()
            } else {
                format!("delete after {} UTC", candidate.expires_at)
            };
            text.push_str(&format!(
                "  {}  ->  {}  {}\n",
                style.object_name(&candidate.name),
                style.object_name(&candidate.archive_name),
                style.muted(&format!("{}, {expiry}", age(candidate.age_days)))
            ));
        }
        text.push_str(&overflow(style, hidden, "  "));
    }
    text.push_str(&in_use(plan, limit, style));
    if !plan.archive_deletions.is_empty() {
        text.push_str(&format!("\n{}\n", style.success("Archives to delete")));
        let (deletions, hidden) = visible(&plan.archive_deletions, limit);
        for deletion in deletions {
            let detail: String = if deletion.archived_in_run {
                "archived in this run".to_owned()
            } else {
                format!(
                    "archived {} UTC, {}, expired {} UTC",
                    deletion.archived_at,
                    age(deletion.age_days),
                    deletion.expires_at
                )
            };
            text.push_str(&format!(
                "  {}  {}\n",
                style.object_name(&deletion.name),
                style.muted(&detail)
            ));
        }
        text.push_str(&overflow(style, hidden, "  "));
    }
    if !plan.retained_archives.is_empty() {
        text.push_str(&format!("\n{}\n", style.success("Retained archives")));
        let (retained_archives, hidden) = visible(&plan.retained_archives, limit);
        for retained in retained_archives {
            text.push_str(&format!(
                "  {}  {}\n",
                style.object_name(&retained.name),
                style.muted(&format!(
                    "archived {} UTC, expires {} UTC",
                    retained.archived_at, retained.expires_at
                ))
            ));
        }
        text.push_str(&overflow(style, hidden, "  "));
    }
    text
}

fn old_name_detail(view: &OldNameViewText) -> (&'static str, String) {
    let expiry: &str = view.expires_on.as_deref().unwrap_or_default();
    match view.drop_reason.as_deref() {
        Some(DROP_EARLY) => ("drop", format!("now  (requested; would expire {expiry})")),
        Some(DROP_EXPIRED) => ("drop", format!("now  (expired {expiry})")),
        _ if view.occupied => {
            let owner: String = view
                .claimed_by
                .as_ref()
                .map_or_else(String::new, |model| format!(", model:{model}"));
            (
                "record",
                format!("dropped  (name now used by another relation{owner})"),
            )
        }
        Some(DROP_MISSING) => ("record", "dropped  (the view no longer exists)".to_owned()),
        _ => (
            "expires",
            format!(
                "{expiry}  (live; drop early with --drop-old-name-view {})",
                view.name
            ),
        ),
    }
}

/// Compatibility views at old model names and what happens to each.
pub(crate) fn old_name_views(
    plan: &JanitorPlanText,
    limit: Option<usize>,
    style: CliStyle,
) -> String {
    let listed: Vec<&OldNameViewText> = plan
        .old_name_drops
        .iter()
        .chain(&plan.old_name_live)
        .chain(&plan.old_name_missing)
        .collect();
    if listed.is_empty() {
        return String::new();
    }
    let mut text: String = format!(
        "\n{} {}\n",
        style.success("Old name views"),
        style.muted(&format!("({})", listed.len()))
    );
    let (shown, hidden) = visible(&listed, limit);
    for (index, view) in shown.iter().enumerate() {
        let last: bool = index + 1 == listed.len();
        text.push_str(&format!(
            "{} {}  {}\n",
            tree_connector(style, last),
            style.object_name(&view.name),
            style.muted(&format!("-> model:{}", view.destination_model))
        ));
        let (label, detail) = old_name_detail(view);
        let indent: String = if last {
            TREE_BLANK.to_owned()
        } else {
            style.muted(TREE_CONTINUATION)
        };
        text.push_str(&format!(
            "{indent}{} {}  {detail}\n",
            tree_connector(style, true),
            style.muted(label)
        ));
    }
    if hidden > 0 {
        text.push_str(&format!(
            "{} {}",
            tree_connector(style, true),
            overflow(style, hidden, "")
        ));
    }
    text
}

/// A titled list of `  name` or `  name  detail` lines, or nothing when empty.
pub(crate) fn listing(
    (style, limit): (CliStyle, Option<usize>),
    title: &str,
    items: &[(String, Option<String>)],
) -> String {
    if items.is_empty() {
        return String::new();
    }
    let mut text: String = format!("\n{}\n", style.success(title));
    let (shown, hidden) = visible(items, limit);
    for (name, detail) in shown {
        match detail {
            Some(detail) => text.push_str(&format!(
                "  {}  {}\n",
                style.object_name(name),
                style.muted(detail)
            )),
            None => text.push_str(&format!("  {}\n", style.object_name(name))),
        }
    }
    text.push_str(&overflow(style, hidden, "  "));
    text
}

/// Skipped objects: each with its reason when `limit` is none, otherwise counted by reason.
pub(crate) fn skipped_objects(
    plan: &JanitorPlanText,
    limit: Option<usize>,
    style: CliStyle,
) -> String {
    let Some(limit) = limit else {
        let skipped: Vec<(String, Option<String>)> = plan
            .skipped_relations
            .iter()
            .map(|(name, reason)| (name.clone(), Some(reason.clone())))
            .collect();
        return listing((style, None), "Skipped objects", &skipped);
    };
    if plan.skipped_relations.is_empty() {
        return String::new();
    }
    let mut groups: Vec<(usize, &str)> = Vec::new();
    for (_, reason) in &plan.skipped_relations {
        match groups
            .iter_mut()
            .find(|(_, known)| *known == reason.as_str())
        {
            Some((count, _)) => *count += 1,
            None => groups.push((1, reason.as_str())),
        }
    }
    groups.sort_by(|left, right| right.0.cmp(&left.0).then_with(|| left.1.cmp(right.1)));
    let width: usize = groups
        .first()
        .map_or(1, |(count, _)| count.to_string().len());
    let mut text: String = format!(
        "\n{} {}\n",
        style.success("Skipped objects"),
        style.muted(&format!("({})", plan.skipped_relations.len()))
    );
    let (shown, hidden) = visible(&groups, Some(limit));
    for (count, reason) in shown {
        text.push_str(&format!(
            "  {}  {}\n",
            style.accent(&format!("{count:>width$}")),
            style.muted(reason)
        ));
    }
    text.push_str(&overflow(style, hidden, "  "));
    text
}
