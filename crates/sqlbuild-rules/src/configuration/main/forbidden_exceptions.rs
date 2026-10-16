//! `forbidden_exceptions`: exceptions or scoped ignores in a project that disallows them.

use sqlbuild_analysis::contracts::main::join_helps::join_helps;
use sqlbuild_core::cli_text::main::format_count_noun::format_count_noun;

use crate::configuration::errors::ConfigPolicyError;
use crate::configuration::main::setting_help::setting_help;
use crate::models::RulesConfig;
use sqlbuild_core::constants::PROJECT_CONFIG_FILENAME as PROJECT_CONFIG_FILE;

/// The policy error when `allow_exceptions = false` and exception or ignore entries exist.
#[must_use]
pub fn forbidden_exceptions(config: &RulesConfig) -> Option<ConfigPolicyError> {
    if config.allow_exceptions {
        return None;
    }
    let mut entries: Vec<String> = Vec::new();
    let mut tables: Vec<String> = Vec::new();
    for (key, count) in [
        ("rule_exceptions", config.rule_exceptions.len()),
        ("rule_ignores", config.rule_ignores.len()),
    ] {
        if count == 0 {
            continue;
        }
        let table: String = format!("[[rules.{key}]]");
        let count: i64 = i64::try_from(count).unwrap_or(i64::MAX);
        entries.push(format_count_noun(
            count,
            &format!("{table} entry"),
            Some(&format!("{table} entries")),
        ));
        tables.push(table);
    }
    if entries.is_empty() {
        return None;
    }
    let message: String = format!(
        "{PROJECT_CONFIG_FILE} has {}, which this project does not allow; \
         {PROJECT_CONFIG_FILE} sets [rules] allow_exceptions = false",
        entries.join(" and ")
    );
    let help: String = join_helps(&[
        format!(
            "remove every {} entry and fix the findings it hides; to turn a Rule off for the \
             whole project, add its code to [rules] ignore",
            tables.join(" and ")
        ),
        setting_help(
            "to allow Rule exceptions, scoped ignores and inline suppressions",
            "rules",
            "allow_exceptions",
            "true",
        ),
    ]);
    Some(ConfigPolicyError { message, help })
}
