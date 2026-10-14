//! The namespace line every scenario command prints first.

use crate::scenario_command::constants::UNSET_NAMESPACE_LABEL;
use crate::scenario_command::models::ScenarioNamespace;

/// `Scenario namespace: <value or (unset)> (source: <source>)` and a newline.
#[must_use]
pub fn render_namespace_header(namespace: &ScenarioNamespace) -> String {
    format!(
        "Scenario namespace: {} (source: {})\n",
        namespace.value.as_deref().unwrap_or(UNSET_NAMESPACE_LABEL),
        namespace.source
    )
}
