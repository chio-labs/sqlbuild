//! The run and model context values templates read through `${ctx.*}`.

use crate::config_values::main::config_entry::config_entry;
use crate::config_values::models::ConfigNode;
use crate::config_values::types::ConfigEntries;
use crate::config_values::types::HostObject;
use crate::model_config_build::constants::{
    ALIAS_KEY, DATABASE_KEY, DESTINATION_DATABASE_CONTEXT, DESTINATION_QUALIFIED_CONTEXT,
    DESTINATION_SCHEMA_CONTEXT, DESTINATION_TABLE_CONTEXT, MODEL_ALIAS_CONTEXT,
    MODEL_DATABASE_CONTEXT, MODEL_NAME_CONTEXT, MODEL_SCHEMA_CONTEXT, RUN_ID_CONTEXT,
    RUN_TARGET_CONTEXT, SCHEMA_KEY,
};
use crate::model_config_build::models::ConfigBuildInputs;
use crate::types::{AuthoredNode, NodeKind};

/// Context entries.
type Entries<H> = ConfigEntries<H>;

fn named<H>(name: &str, value: ConfigNode<H>) -> (ConfigNode<H>, ConfigNode<H>) {
    (ConfigNode::Str(name.to_owned()), value)
}

/// The value of `key` when it is a string, as `isinstance(raw, str)` keeps it.
pub(crate) fn string_entry<H: HostObject>(
    values: &[(ConfigNode<H>, ConfigNode<H>)],
    key: &str,
) -> Option<ConfigNode<H>> {
    config_entry(values, key)
        .filter(|value| value.kind() == NodeKind::Str)
        .cloned()
}

/// `build_run_context_values`: the run's id and target.
pub(crate) fn run_context<H: HostObject>(inputs: &ConfigBuildInputs<H>) -> Entries<H> {
    vec![
        named(RUN_ID_CONTEXT, inputs.run_id.clone()),
        named(RUN_TARGET_CONTEXT, inputs.target_name.clone()),
    ]
}

fn text_of<H: HostObject>(value: &ConfigNode<H>) -> String {
    value.text().unwrap_or_default()
}

/// `build_model_context_values` for a model's config values.
pub(crate) fn model_context<H: HostObject>(
    inputs: &ConfigBuildInputs<H>,
    values: &[(ConfigNode<H>, ConfigNode<H>)],
    model_name: &str,
    include_target_values: bool,
) -> Entries<H> {
    let database: Option<ConfigNode<H>> = string_entry(values, DATABASE_KEY);
    let schema: Option<ConfigNode<H>> = string_entry(values, SCHEMA_KEY);
    let alias: ConfigNode<H> =
        string_entry(values, ALIAS_KEY).unwrap_or_else(|| ConfigNode::Str(model_name.to_owned()));
    let or_null = |value: &Option<ConfigNode<H>>| value.clone().unwrap_or(ConfigNode::Null);
    let mut context: Entries<H> = run_context(inputs);
    context.extend([
        named(MODEL_NAME_CONTEXT, ConfigNode::Str(model_name.to_owned())),
        named(MODEL_DATABASE_CONTEXT, or_null(&database)),
        named(MODEL_SCHEMA_CONTEXT, or_null(&schema)),
        named(MODEL_ALIAS_CONTEXT, alias.clone()),
    ]);
    if !include_target_values {
        return context;
    }
    let qualified: ConfigNode<H> = match (&database, &schema) {
        (Some(database), Some(schema)) => ConfigNode::Str(format!(
            "{}.{}.{}",
            text_of(database),
            text_of(schema),
            text_of(&alias)
        )),
        (None, Some(schema)) => ConfigNode::Str(format!("{}.{}", text_of(schema), text_of(&alias))),
        _ => ConfigNode::Null,
    };
    context.extend([
        named(DESTINATION_DATABASE_CONTEXT, or_null(&database)),
        named(DESTINATION_SCHEMA_CONTEXT, or_null(&schema)),
        named(DESTINATION_TABLE_CONTEXT, alias),
        named(DESTINATION_QUALIFIED_CONTEXT, qualified),
    ]);
    context
}
