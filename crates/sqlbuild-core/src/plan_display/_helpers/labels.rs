//! The snapshot label shared by plan summaries and progress rows.

use crate::plan_display::constants::SNAPSHOT;
use crate::plan_display::models::ModelLabelFacts;

/// The snapshot strategy and historical input, optionally as `snapshot (<details>)`.
pub(crate) fn snapshot_label(entry: &ModelLabelFacts, include_prefix: bool) -> String {
    let mut parts: Vec<String> = Vec::new();
    if let Some(strategy) = entry
        .snapshot_strategy
        .as_deref()
        .filter(|strategy| !strategy.is_empty())
    {
        parts.push(strategy.to_owned());
    }
    if entry.historical {
        let input: &str = entry
            .historical_input
            .as_deref()
            .filter(|input| !input.is_empty())
            .unwrap_or(SNAPSHOT);
        parts.push(format!("historical {input}"));
    }
    if parts.is_empty() {
        return if include_prefix {
            SNAPSHOT.to_owned()
        } else {
            String::new()
        };
    }
    let label: String = parts.join(", ");
    if include_prefix {
        return format!("snapshot ({label})");
    }
    label
}
