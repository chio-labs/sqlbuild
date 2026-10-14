//! The inspection text of one rule.

use crate::models::RulesConfig;
use crate::rule_catalogue::_helpers::thresholds::threshold_lines;
use crate::rule_catalogue::constants::{MINIMUM_RULES_CODES, TEST_RULE_PREFIX};
use crate::rule_catalogue::models::RuleText;

/// `sqb rules show` text, with effective thresholds and test paths when a config is given.
pub fn format_rule_text(rule: &RuleText, config: Option<&RulesConfig>) -> String {
    let mut lines: Vec<String> = vec![
        format!("{}: {}", rule.code, rule.slug),
        format!("Family: {}", rule.family),
        format!(
            "Enabled by default: {}",
            if rule.enabled_by_default { "yes" } else { "no" }
        ),
        format!("Kind: {}", if rule.custom { "custom" } else { "built-in" }),
        String::new(),
        rule.message.clone(),
        String::new(),
        format!("Remediation: {}", rule.remediation),
    ];
    if let Some(source) = &rule.source {
        lines.extend([String::new(), format!("Source: {source}")]);
    }
    if !rule.options.is_empty() {
        lines.extend([String::new(), "Options:".into()]);
        for option in &rule.options {
            lines.push(format!(
                "- {}: default={} ({})",
                option.name, option.default_repr, option.description
            ));
        }
    }
    if let Some(config) = config {
        if MINIMUM_RULES_CODES.contains(&rule.code.as_str()) {
            lines.extend([String::new(), "Effective thresholds:".into()]);
            lines.extend(threshold_lines(config));
        }
        if rule.code.starts_with(TEST_RULE_PREFIX) {
            lines.extend([
                String::new(),
                "Effective SQL test paths:".into(),
                "- Unit tests: tests/unit/".into(),
                "- Scenarios: tests/scenarios/".into(),
                format!(
                    "- Cross-domain pipelines: tests/unit/{}/",
                    config.sql_tests.pipeline_directory
                ),
            ]);
        }
    }
    lines.join("\n")
}
