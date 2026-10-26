//! `invocation_origin`: whether an integration, a CI system or a person ran an invocation.

use crate::records::constants::{
    CI_DISABLED_VALUES, CI_ENVIRONMENT_VARIABLES, CI_ORIGIN, INTEGRATION_ORIGIN, LOCAL_ORIGIN,
};

/// `integration` when an integration supplied external context, `ci` when `environment` names a CI system, else `local`.
#[must_use]
pub fn invocation_origin(
    has_external_context: bool,
    environment: impl Fn(&str) -> Option<String>,
) -> &'static str {
    if has_external_context {
        return INTEGRATION_ORIGIN;
    }
    let set = |name: &str| {
        environment(name).is_some_and(|value| {
            let value: String = value.trim().to_ascii_lowercase();
            !value.is_empty() && !CI_DISABLED_VALUES.contains(&value.as_str())
        })
    };
    if CI_ENVIRONMENT_VARIABLES.iter().any(|name| set(name)) {
        CI_ORIGIN
    } else {
        LOCAL_ORIGIN
    }
}
