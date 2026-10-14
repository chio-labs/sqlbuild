//! Effective rule test thresholds rendered as guidance lines.

use std::collections::BTreeMap;

use crate::models::RulesConfig;
use crate::rule_catalogue::_helpers::python_repr::dict_repr;
use crate::rule_catalogue::constants::THRESHOLD_DEFAULTS;

/// Global and path-scoped thresholds in deterministic authored order.
pub(crate) fn threshold_lines(config: &RulesConfig) -> Vec<String> {
    let mut thresholds: BTreeMap<&str, u32> = THRESHOLD_DEFAULTS.into_iter().collect();
    for (name, value) in &config.thresholds {
        thresholds.insert(name, *value);
    }
    let mut lines: Vec<String> = thresholds
        .iter()
        .map(|(name, value)| format!("- `{name}` = `{value}`"))
        .collect();
    for (index, entry) in config.threshold_overrides.iter().enumerate() {
        let values: String = dict_repr(
            entry
                .thresholds
                .iter()
                .map(|(name, value)| (name.as_str(), value.to_string())),
        );
        lines.push(format!(
            "- Override {} at `{}`: `{values}` ({})",
            index + 1,
            entry.paths.join(","),
            entry.reason
        ));
    }
    if !config.threshold_overrides.is_empty() {
        lines.push("- Matching overrides apply in authored order; the last match wins.".into());
    }
    lines
}
