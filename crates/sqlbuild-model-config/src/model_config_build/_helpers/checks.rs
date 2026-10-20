//! The header, hook and macro checks of one model's config build.

use crate::config_presence::main::entry_macro_path::entry_macro_path;
use crate::config_presence::models::MacroPath;
use crate::config_values::main::config_entry::config_entry;
use crate::config_values::main::set_config_entry::set_config_entry;
use crate::config_values::models::ConfigNode;
use crate::config_values::types::HostObject;
use crate::errors::ConfigError;
use crate::model_config_build::constants::{HOOK_KEYS, SORTED_HOOK_KEYS, TAGS_KEY};
use crate::model_config_build::models::{ConfigBuildHalt, HeaderEntryFacts};
use crate::model_config_build::types::{ConfigBuildHost, HostHalt, HostNode};
use crate::types::{AuthoredNode, NodeKind};

/// The `CompileInputError` `model '<name>' <text>`.
pub(crate) fn model_error(model_name: &str, text: &str) -> ConfigError {
    ConfigError::compile(format!("model '{model_name}' {text}"))
}

/// `_validate_model_header_tags`.
pub(crate) fn check_header_tags<H: HostObject>(
    header: &[(ConfigNode<H>, ConfigNode<H>)],
    model_name: &str,
) -> Result<(), ConfigError> {
    let Some(tags) = set_config_entry(header, TAGS_KEY) else {
        return Ok(());
    };
    if tags.kind() != NodeKind::List {
        return Err(model_error(model_name, "tags must be a list"));
    }
    if tags.items().iter().all(|tag| tag.kind() == NodeKind::Str) {
        Ok(())
    } else {
        Err(model_error(model_name, "tags entries must be strings"))
    }
}

/// Whether every item of a hook list is a typed hook entry, checked in order.
fn all_hook_entries<B: ConfigBuildHost>(
    host: &B,
    value: &HostNode<B>,
) -> Result<bool, HostHalt<B>> {
    for item in (&value).items() {
        let typed: bool = match item {
            ConfigNode::Host(_) => host.typed_hook_entry(item).map_err(ConfigBuildHalt::Host)?,
            _ => false,
        };
        if !typed {
            return Ok(false);
        }
    }
    Ok(true)
}

/// `validate_model_hook_config`: every hook list holds typed hook entries only.
pub(crate) fn check_hooks<B: ConfigBuildHost>(
    host: &B,
    values: &[(HostNode<B>, HostNode<B>)],
    model_name: &str,
) -> Result<(), HostHalt<B>> {
    let config = ConfigBuildHalt::Config;
    for key in SORTED_HOOK_KEYS {
        let Some(value) = config_entry(values, key) else {
            continue;
        };
        if !matches!(value.kind(), NodeKind::List | NodeKind::Tuple) {
            return Err(config(model_error(
                model_name,
                &format!("{key} must be a list of typed hook entries"),
            )));
        }
        if !all_hook_entries(host, value)? {
            return Err(config(model_error(
                model_name,
                &format!(
                    "{key} entries must use typed inline_sql(...), sql(...), or python(...) hook syntax"
                ),
            )));
        }
    }
    Ok(())
}

/// The facts of `key` when its value is still the header's own.
pub(crate) fn own_facts<'a>(
    facts: Option<&'a [(String, HeaderEntryFacts)]>,
    own: &[String],
    key: &str,
) -> Option<&'a HeaderEntryFacts> {
    if !own.iter().any(|name| name == key) {
        return None;
    }
    facts?
        .iter()
        .find(|(name, _)| name == key)
        .map(|(_, facts)| facts)
}

/// The exact text of a string key the header facts are found by.
pub(crate) fn key_text<H: HostObject>(key: &ConfigNode<H>) -> Option<String> {
    match key {
        ConfigNode::Str(text) => Some(text.clone()),
        ConfigNode::Host(host) if host.facts.strict_text => host.facts.text.clone(),
        _ => None,
    }
}

/// The first config field outside hooks holding a macro call, as Python's walk reports it.
pub(crate) fn check_no_config_macros<H: HostObject>(
    values: &[(ConfigNode<H>, ConfigNode<H>)],
    facts: Option<&[(String, HeaderEntryFacts)]>,
    own: &[String],
) -> Result<(), ConfigError> {
    for (key, value) in values {
        if HOOK_KEYS.iter().any(|name| key.is_text(name)) {
            continue;
        }
        let found: MacroPath = match key_text(key).and_then(|name| own_facts(facts, own, &name)) {
            Some(facts) => facts.macro_path.clone(),
            None => entry_macro_path(&key, &value),
        };
        if let MacroPath::Found(path) = found {
            return Err(ConfigError::compile(format!(
                "model config field '{}' does not allow macros",
                path.join(".")
            )));
        }
    }
    Ok(())
}
