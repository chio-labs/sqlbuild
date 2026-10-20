//! A model's layers merged, with which header entries are still the header's own values.

use crate::config_values::main::layered_config::layered_config;
use crate::config_values::models::ConfigNode;
use crate::config_values::types::ConfigEntries;
use crate::config_values::types::HostObject;
use crate::model_config_build::_helpers::checks::key_text;
use crate::model_config_build::constants::{TAGS_KEY, TEMPLATE_OPEN_TOKEN};
use crate::model_config_build::models::{ConfigBuildHalt, ConfigBuildInputs};
use crate::model_config_build::types::{ConfigBuildHost, HostEntries, HostHalt, HostNode};
use crate::types::{AuthoredNode, NodeKind};

/// Config entries.
pub(crate) type Entries<H> = ConfigEntries<H>;

/// A fresh copy of the project defaults, with its own `tags` list.
pub(crate) fn project_defaults<H: HostObject>(inputs: &ConfigBuildInputs<H>) -> Entries<H> {
    inputs
        .defaults
        .iter()
        .map(|(key, value)| match value {
            ConfigNode::List(items) if key.is_text(TAGS_KEY) => {
                (key.clone(), ConfigNode::List(items.clone()))
            }
            _ => (key.clone(), value.clone()),
        })
        .collect()
}

/// The path default `key`'s entries.
pub(crate) fn path_default_values<'a, H: HostObject, E>(
    inputs: &'a ConfigBuildInputs<H>,
    key: &str,
) -> Result<&'a Entries<H>, ConfigBuildHalt<H, E>> {
    inputs
        .path_defaults
        .iter()
        .find(|(name, _)| name == key)
        .map(|(_, values)| values)
        .ok_or_else(|| ConfigBuildHalt::MissingPathDefault(key.to_owned()))
}

/// `overlay` over `base`, and the overlay's keys whose merged value is still the overlay's own.
pub(crate) fn layered_own<B: ConfigBuildHost>(
    host: &B,
    base: &HostEntries<B>,
    overlay: &[(HostNode<B>, HostNode<B>)],
) -> Result<(HostEntries<B>, Vec<String>), HostHalt<B>> {
    let text = |item: &HostNode<B>| host.python_str(item, false);
    let layered = layered_config(base, overlay, &text).map_err(ConfigBuildHalt::Host)?;
    let own: Vec<String> = overlay
        .iter()
        .filter_map(|(key, _)| key_text(key))
        .filter(|name| !layered.unioned_keys.contains(&name.as_str()))
        .collect();
    Ok((layered.entries, own))
}

/// Whether expansion keeps `value` as the same object: a string without a template, or a non-container.
pub(crate) fn kept_by_expansion<H: HostObject>(value: &ConfigNode<H>) -> bool {
    match value.kind() {
        NodeKind::Str => !value
            .with_text(|text| text.contains(TEMPLATE_OPEN_TOKEN))
            .unwrap_or(false),
        NodeKind::Map | NodeKind::List | NodeKind::Tuple => false,
        _ => true,
    }
}

/// Whether the entry named `name` in `values` keeps its value through an expansion.
fn kept_entry<H: HostObject>(values: &Entries<H>, name: &str) -> bool {
    values
        .iter()
        .find(|(key, _)| key_text(key).as_deref() == Some(name))
        .is_some_and(|(_, value)| kept_by_expansion(value))
}

/// The own keys whose values an expansion of `values` keeps.
pub(crate) fn kept_own<H: HostObject>(values: &Entries<H>, own: Vec<String>) -> Vec<String> {
    own.into_iter()
        .filter(|name| kept_entry(values, name))
        .collect()
}
