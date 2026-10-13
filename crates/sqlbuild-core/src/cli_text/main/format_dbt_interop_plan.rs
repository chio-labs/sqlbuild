//! The human `sqb dbt` plan.

use crate::cli_text::_helpers::dbt_plan::{
    dbt_section, sqlbuild_section, trailing_sections, without_ansi,
};
use crate::cli_text::_helpers::layout::surface_header;
use crate::cli_text::models::{CliStyle, DbtInteropPlanText, DisplayLimit};

/// Selected dbt and SQLBuild work, colored or plain; `sqlbuild_plan` is the rendered SQLBuild plan.
#[must_use]
pub fn format_dbt_interop_plan(
    plan: &DbtInteropPlanText,
    sqlbuild_plan: Option<&str>,
    (display, use_color): (&DisplayLimit, bool),
) -> String {
    let mut dbt_ids: Vec<&String> = plan
        .dbt_selected_unique_ids
        .iter()
        .chain(&plan.dbt_required_unique_ids)
        .collect();
    dbt_ids.sort_unstable();
    dbt_ids.dedup();
    let selected: usize = dbt_ids.len() + plan.sqlbuild_models.len();
    let mut lines: Vec<String> = vec![
        surface_header(
            CliStyle { use_color: true },
            "Plan ready",
            &format!("{selected} selected resources"),
        ),
        String::new(),
    ];
    lines.extend(dbt_section(plan, display));
    lines.push(String::new());
    lines.extend(sqlbuild_section(plan, sqlbuild_plan, display));
    lines.extend(trailing_sections(plan, display));
    let text: String = lines.join("\n");
    if use_color { text } else { without_ansi(&text) }
}
