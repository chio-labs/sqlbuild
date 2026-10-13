//! Scenario lifecycle progress labelled with the effective namespace.

use crate::scenario_command::constants::UNSET_NAMESPACE_LABEL;
use crate::scenario_command::models::ScenarioNamespace;

/// `<activity> (namespace: <value or (unset)>; source: <source>)`.
#[must_use]
pub fn scenario_activity_message(activity: &str, namespace: &ScenarioNamespace) -> String {
    format!(
        "{activity} (namespace: {}; source: {})",
        namespace.value.as_deref().unwrap_or(UNSET_NAMESPACE_LABEL),
        namespace.source
    )
}
