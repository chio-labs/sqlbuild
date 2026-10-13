//! The janitor plan preview.

use crate::cli_text::models::CliStyle;
use crate::janitor_text::_helpers::counts::environment_label;
use crate::janitor_text::_helpers::plan_sections::{
    archives, blocked, listing, old_name_views, summary,
};
use crate::janitor_text::models::JanitorPlanText;

/// Every section of the preview, ending with a blank line.
#[must_use]
pub fn render_janitor_plan(plan: &JanitorPlanText, style: CliStyle) -> String {
    let mut text: String = format!(
        "{}  {}\n\n",
        style.title("Janitor preview"),
        style.object_name(environment_label(plan))
    );
    text.push_str(&summary(plan, style));
    text.push_str(&blocked(plan, style));
    let skipped_schemas: Vec<(String, Option<String>)> = plan
        .skipped_schemas
        .iter()
        .map(|schema| {
            (
                schema.name.clone(),
                Some(format!(
                    "contains active source {}",
                    schema.source_names.join(", ")
                )),
            )
        })
        .collect();
    text.push_str(&listing(style, "Skipped schemas", &skipped_schemas));
    if !plan.direct_mode {
        let candidates: Vec<(String, Option<String>)> = plan
            .candidates
            .iter()
            .map(|name| (name.clone(), None))
            .collect();
        text.push_str(&listing(style, "Eligible objects", &candidates));
    }
    text.push_str(&archives(plan, style));
    text.push_str(&old_name_views(plan, style));
    let artifacts: Vec<(String, Option<String>)> = plan
        .query_artifacts
        .iter()
        .map(|name| (name.clone(), None))
        .collect();
    text.push_str(&listing(
        style,
        "Eligible expired query artifacts",
        &artifacts,
    ));
    let prunes: Vec<(String, Option<String>)> = plan
        .state_prunes
        .iter()
        .map(|(name, versions)| (name.clone(), Some(format!("keep latest {versions}"))))
        .collect();
    text.push_str(&listing(style, "Eligible direct state pruning", &prunes));
    let skipped: Vec<(String, Option<String>)> = plan
        .skipped_relations
        .iter()
        .map(|(name, reason)| (name.clone(), Some(reason.clone())))
        .collect();
    text.push_str(&listing(style, "Skipped objects", &skipped));
    text.push('\n');
    text
}
