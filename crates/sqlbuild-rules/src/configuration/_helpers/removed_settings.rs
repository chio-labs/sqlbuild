//! `[rules]` settings SQLBuild no longer supports, with how to migrate.

use sqlbuild_analysis::contracts::main::join_helps::join_helps;
use sqlbuild_core::constants::PROJECT_CONFIG_FILENAME as PROJECT_CONFIG_FILE;

use crate::configuration::errors::ConfigPolicyError;
use crate::constants::REMOVED_ALLOW_EXCEPTIONS;

/// The error for a `[rules]` table that still sets a removed setting.
pub(crate) fn removed_settings(rules: &toml::Table) -> Option<ConfigPolicyError> {
    if !rules.contains_key(REMOVED_ALLOW_EXCEPTIONS) {
        return None;
    }
    let message: String = format!(
        "{PROJECT_CONFIG_FILE} sets [rules] {REMOVED_ALLOW_EXCEPTIONS}, which SQLBuild no longer \
         supports: Rule exceptions are declared only in {PROJECT_CONFIG_FILE}, where review sees \
         them, and inline -- sqb: ignore suppressions were removed"
    );
    let help: String = join_helps(&[
        format!("remove the {REMOVED_ALLOW_EXCEPTIONS} line from [rules] in {PROJECT_CONFIG_FILE}"),
        "keep each reviewed deviation as a [[rules.rule_exceptions]] entry with rule, path and \
         reason, or turn a Rule off for the whole project with [rules] ignore"
            .to_owned(),
    ]);
    Some(ConfigPolicyError { message, help })
}
