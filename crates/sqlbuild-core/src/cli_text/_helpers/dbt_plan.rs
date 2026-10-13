//! Sections of the `sqb dbt` plan text.

use std::collections::BTreeMap;

use crate::cli_text::_helpers::layout::tree_connector;
use crate::cli_text::_helpers::summary_text::overflow_line;
use crate::cli_text::constants::DBT_RESOURCE_FALLBACK_TYPE;
use crate::cli_text::models::{CliStyle, DbtInteropPlanText, DbtLsNodeText, DisplayLimit};
use crate::text::main::python_splitlines::python_splitlines;

const STYLE: CliStyle = CliStyle { use_color: true };

/// `visible_entries`: the entries shown under the display cap.
fn visible<T>(entries: &[T], display: &DisplayLimit) -> usize {
    display
        .max_entries
        .map_or(entries.len(), |limit| limit.min(entries.len()))
}

fn display_name(node: &DbtLsNodeText) -> String {
    if !node.fqn.is_empty() {
        return node.fqn.join(".");
    }
    node.name
        .clone()
        .filter(|name| !name.is_empty())
        .unwrap_or_else(|| node.unique_id.clone())
}

fn node_lines(nodes: &[&DbtLsNodeText], display: &DisplayLimit) -> Vec<String> {
    let shown: usize = visible(nodes, display);
    let mut lines: Vec<String> = Vec::new();
    for (index, node) in nodes[..shown].iter().enumerate() {
        let last: bool = index + 1 == shown && nodes.len() <= shown;
        lines.push(format!(
            "  {} {}",
            tree_connector(STYLE, last),
            STYLE.object_name(&display_name(node))
        ));
    }
    let hidden: i64 = i64::try_from(nodes.len() - shown).unwrap_or(i64::MAX);
    lines.extend(overflow_line(hidden, "    ", &display.overflow_flag));
    lines
}

/// The dbt section: counts, command, selected nodes by resource type and required ids.
pub(crate) fn dbt_section(plan: &DbtInteropPlanText, display: &DisplayLimit) -> Vec<String> {
    let required: &[String] = &plan.dbt_required_unique_ids;
    let mut lines: Vec<String> = vec![format!(
        "{} {}",
        STYLE.dbt_label("dbt"),
        STYLE.dbt_section(&format!(
            "({} selected, {} required)",
            plan.dbt_selected_unique_ids.len(),
            required.len()
        ))
    )];
    if plan.dbt_skip_reason.is_some() {
        lines.push(STYLE.muted("  skipped: no dbt work selected"));
        return lines;
    }
    lines.push(format!(
        "  {}: {}",
        STYLE.label("command"),
        STYLE.command(&plan.dbt_argv.join(" "))
    ));
    let mut sorted: Vec<(String, String, &DbtLsNodeText)> = plan
        .dbt_nodes
        .iter()
        .map(|node| {
            (
                node.resource_type.clone().unwrap_or_default(),
                display_name(node),
                node,
            )
        })
        .collect();
    sorted.sort_by(|left, right| (&left.0, &left.1).cmp(&(&right.0, &right.1)));
    let mut by_type: BTreeMap<String, Vec<&DbtLsNodeText>> = BTreeMap::new();
    for (_, _, node) in sorted {
        let resource_type: String = node
            .resource_type
            .clone()
            .filter(|kind| !kind.is_empty())
            .unwrap_or_else(|| DBT_RESOURCE_FALLBACK_TYPE.to_owned());
        by_type.entry(resource_type).or_default().push(node);
    }
    for (resource_type, nodes) in &by_type {
        lines.push(String::new());
        lines.push(format!(
            "  {}",
            STYLE.plan_section(&format!("{resource_type} ({})", nodes.len()))
        ));
        lines.extend(node_lines(nodes, display));
    }
    if !required.is_empty() {
        lines.push(String::new());
        lines.push(STYLE.dbt_label(&format!("  required ({})", required.len())));
        let shown: usize = visible(required, display);
        for (index, unique_id) in required[..shown].iter().enumerate() {
            lines.push(format!(
                "  {} {}",
                tree_connector(STYLE, index + 1 == shown),
                STYLE.object_name(unique_id)
            ));
        }
    }
    lines
}

/// The SQLBuild section: the rendered SQLBuild plan, or the selected model names.
pub(crate) fn sqlbuild_section(
    plan: &DbtInteropPlanText,
    sqlbuild_plan: Option<&str>,
    display: &DisplayLimit,
) -> Vec<String> {
    let mut lines: Vec<String> =
        vec![STYLE.plan_section(&format!("SQLBuild ({})", plan.sqlbuild_models.len()))];
    if plan.sqlbuild_skip_reason.is_some() {
        lines.push(STYLE.muted("  skipped: no SQLBuild work selected"));
        return lines;
    }
    if let Some(rendered) = sqlbuild_plan {
        lines.extend(python_splitlines(rendered).into_iter().map(|line| {
            if line.is_empty() {
                String::new()
            } else {
                format!("  {line}")
            }
        }));
        return lines;
    }
    let shown: usize = visible(&plan.sqlbuild_models, display);
    lines.extend(
        plan.sqlbuild_models[..shown]
            .iter()
            .map(|name| format!("  {}", STYLE.object_name(name))),
    );
    lines
}

/// Anchor terms, path translations and warnings, each after a blank line when present.
pub(crate) fn trailing_sections(plan: &DbtInteropPlanText, display: &DisplayLimit) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    if !plan.anchors.is_empty() {
        lines.push(String::new());
        lines.push(STYLE.label("dbt selector anchors"));
        let shown: usize = visible(&plan.anchors, display);
        for (term, unique_ids) in &plan.anchors[..shown] {
            lines.push(format!(
                "  {}: {} dbt resources",
                STYLE.command(term),
                unique_ids.len()
            ));
        }
    }
    if !plan.path_translations.is_empty() {
        lines.push(String::new());
        lines.push(STYLE.label("path translations"));
        for (original, translated) in &plan.path_translations {
            lines.push(format!(
                "  {} -> {}",
                STYLE.command(original),
                STYLE.command(translated)
            ));
        }
    }
    if !plan.warnings.is_empty() {
        lines.push(String::new());
        lines.push(STYLE.warning("Warnings"));
        for warning in &plan.warnings {
            lines.push(STYLE.warning(&format!("  {warning}")));
        }
    }
    lines
}

/// The text with every `ESC[...m` color sequence removed.
pub(crate) fn without_ansi(text: &str) -> String {
    let mut result: String = String::with_capacity(text.len());
    let mut rest: &str = text;
    while let Some(start) = rest.find("\x1b[") {
        result.push_str(&rest[..start]);
        let after: &str = &rest[start + 2..];
        let digits: usize = after
            .find(|character: char| !(character.is_ascii_digit() || character == ';'))
            .unwrap_or(after.len());
        if after[digits..].starts_with('m') {
            rest = &after[digits + 1..];
        } else {
            result.push_str("\x1b[");
            rest = after;
        }
    }
    result.push_str(rest);
    result
}
