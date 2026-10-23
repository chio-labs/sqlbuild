//! The janitor plan preview.

use crate::cli_text::models::CliStyle;
use crate::janitor_text::_helpers::counts::environment_label;
use crate::janitor_text::_helpers::plan_sections::{
    archives, blocked, listing, old_name_views, skipped_objects, summary,
};
use crate::janitor_text::constants::PREVIEW_LIMIT;
use crate::janitor_text::models::JanitorPlanText;

/// Every preview section, capped and grouped unless `verbose`, ending with a blank line.
#[must_use]
pub fn render_janitor_plan(plan: &JanitorPlanText, verbose: bool, style: CliStyle) -> String {
    let limit: Option<usize> = (!verbose).then_some(PREVIEW_LIMIT);
    let mut text: String = format!(
        "{}  {}\n\n",
        style.title("Janitor preview"),
        style.object_name(environment_label(plan))
    );
    text.push_str(&summary(plan, style));
    text.push_str(&blocked(plan, limit, style));
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
    text.push_str(&listing(
        (style, limit),
        "Skipped schemas",
        &skipped_schemas,
    ));
    if !plan.direct_mode {
        let candidates: Vec<(String, Option<String>)> = plan
            .candidates
            .iter()
            .map(|name| (name.clone(), None))
            .collect();
        text.push_str(&listing((style, limit), "Eligible objects", &candidates));
    }
    text.push_str(&archives(plan, limit, style));
    text.push_str(&old_name_views(plan, limit, style));
    let artifacts: Vec<(String, Option<String>)> = plan
        .query_artifacts
        .iter()
        .map(|name| (name.clone(), None))
        .collect();
    text.push_str(&listing(
        (style, limit),
        "Eligible expired query artifacts",
        &artifacts,
    ));
    let review_schemas: Vec<(String, Option<String>)> = plan
        .review_schemas
        .iter()
        .map(|name| (name.clone(), None))
        .collect();
    text.push_str(&listing(
        (style, limit),
        "Leftover review schemas",
        &review_schemas,
    ));
    let prunes: Vec<(String, Option<String>)> = plan
        .state_prunes
        .iter()
        .map(|(name, versions)| (name.clone(), Some(format!("keep latest {versions}"))))
        .collect();
    text.push_str(&listing(
        (style, limit),
        "Eligible direct state pruning",
        &prunes,
    ));
    text.push_str(&skipped_objects(plan, limit, style));
    text.push('\n');
    text
}
