//! A multi-line stale-selection warning: summary, capped bullet list and one hint.

use crate::planner_identity::constants::STALE_TRIGGER_DISPLAY_LIMIT;

/// The warning text for `model_name` building on stale `trigger_names`.
pub fn stale_upstream_warning_message(
    (model_label, model_name): (&str, &str),
    trigger_label: &str,
    trigger_names: &[String],
) -> String {
    let count: usize = trigger_names.len();
    let mut lines: Vec<String> = vec![format!(
        "{model_label} '{model_name}' will build on {count} stale {trigger_label} not selected for rebuild:"
    )];
    for name in trigger_names.iter().take(STALE_TRIGGER_DISPLAY_LIMIT) {
        lines.push(format!("    - {name}"));
    }
    if count > STALE_TRIGGER_DISPLAY_LIMIT {
        lines.push(format!("    +{} more", count - STALE_TRIGGER_DISPLAY_LIMIT));
    }
    lines.push(format!(
        "    rebuild the closure to refresh them: --select +{model_name}"
    ));
    lines.join("\n")
}
