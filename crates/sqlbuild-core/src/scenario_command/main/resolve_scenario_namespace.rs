//! The effective scenario run namespace.

use crate::scenario_command::constants::{
    CLI_SOURCE, ENV_SOURCE, INVALID_NAMESPACE_CODE, LOCAL_CONFIG_SOURCE, MAX_NAMESPACE_LENGTH,
    PROJECT_CONFIG_SOURCE, UNSET_NAMESPACE_SOURCE,
};
use crate::scenario_command::errors::ScenarioCommandError;
use crate::scenario_command::models::{NamespaceCandidates, ScenarioNamespace};

fn is_valid(value: &str) -> bool {
    (1..=MAX_NAMESPACE_LENGTH).contains(&value.len())
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'.' | b'-'))
}

/// CLI, then environment, then local config, then project config; the first set value must be valid.
pub fn resolve_scenario_namespace(
    candidates: NamespaceCandidates,
) -> Result<ScenarioNamespace, ScenarioCommandError> {
    let ordered: [(Option<String>, &str); 4] = [
        (candidates.cli, CLI_SOURCE),
        (candidates.env, ENV_SOURCE),
        (candidates.local_config, LOCAL_CONFIG_SOURCE),
        (candidates.project_config, PROJECT_CONFIG_SOURCE),
    ];
    for (value, source) in ordered {
        let Some(value) = value else {
            continue;
        };
        if !is_valid(&value) {
            return Err(ScenarioCommandError {
                code: INVALID_NAMESPACE_CODE,
                message: "scenario.run_namespace must be 1–128 characters: ASCII letters, \
                          digits, '-', '_' or '.'"
                    .to_owned(),
                help: None,
            });
        }
        return Ok(ScenarioNamespace {
            value: Some(value),
            source: source.to_owned(),
        });
    }
    Ok(ScenarioNamespace {
        value: None,
        source: UNSET_NAMESPACE_SOURCE.to_owned(),
    })
}
