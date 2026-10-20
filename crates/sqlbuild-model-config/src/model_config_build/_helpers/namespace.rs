//! The target namespace applied over a model's values, as `apply_environment_database_schema_overrides`.

use crate::config_values::main::inserted_entry::inserted_entry;
use crate::config_values::models::ConfigNode;
use crate::config_values::types::ConfigEntries;
use crate::errors::ConfigError;
use crate::model_config_build::_helpers::context::model_context;
use crate::model_config_build::_helpers::expansion::{ExpansionSources, expand_value};
use crate::model_config_build::constants::{
    DATABASE_KEY, ENVIRONMENT_DATABASE_LABEL, ENVIRONMENT_SCHEMA_LABEL, PRESERVE_TARGET_VALUE,
    SCHEMA_KEY,
};
use crate::model_config_build::models::{ConfigBuildHalt, ConfigBuildInputs};
use crate::model_config_build::types::{ConfigBuildHost, HostHalt};
use crate::types::AuthoredNode;

/// Config entries.
type Entries<H> = ConfigEntries<H>;

/// The namespaced values, the keys the target replaced, and the reads its expansions made.
pub(crate) struct Namespaced<H> {
    pub(crate) values: Entries<H>,
    pub(crate) replaced: Vec<&'static str>,
    pub(crate) reads: Vec<(&'static str, String)>,
}

/// One model's values with the target's database and schema expanded over them.
pub(crate) fn namespaced_values<B: ConfigBuildHost>(
    (host, inputs): (&B, &ConfigBuildInputs<B::Handle>),
    values: &Entries<B::Handle>,
    logical: (bool, bool),
    model_name: &str,
) -> Result<Namespaced<B::Handle>, HostHalt<B>> {
    let mut namespaced = Namespaced {
        values: values.clone(),
        replaced: Vec::new(),
        reads: Vec::new(),
    };
    let Some((database, schema)) = &inputs.target_namespace else {
        return Ok(namespaced);
    };
    let (logical_database, logical_schema) = logical;
    let namespace = [
        (
            DATABASE_KEY,
            database,
            logical_database,
            ENVIRONMENT_DATABASE_LABEL,
        ),
        (SCHEMA_KEY, schema, logical_schema, ENVIRONMENT_SCHEMA_LABEL),
    ];
    let preserved = |value: &ConfigNode<B::Handle>| value.is_text(PRESERVE_TARGET_VALUE);
    let missing: Vec<&str> = namespace
        .iter()
        .filter(|(_, value, logical, _)| preserved(value) && !logical)
        .map(|(key, _, _, _)| *key)
        .collect();
    if !missing.is_empty() {
        let dimensions: String = missing.join(" and ");
        return Err(ConfigBuildHalt::Config(
            ConfigError::compile(format!(
                "Model '{model_name}' has no logical {dimensions}, but the selected target sets \
                 {dimensions} to 'preserve'"
            ))
            .with_help(format!(
                "Set {dimensions} on the resource or its defaults, or configure a literal \
                 target {dimensions}."
            )),
        ));
    }
    let context: Entries<B::Handle> = model_context(inputs, values, model_name, false);
    for (key, value, _, label) in namespace {
        if matches!(value, ConfigNode::Null) || preserved(value) {
            continue;
        }
        let sources: ExpansionSources<'_, B> = ExpansionSources {
            host,
            variables: &inputs.variables,
            context: context.clone(),
        };
        let (expanded, reads) = expand_value(sources, value, (false, label));
        namespaced.reads.extend(reads);
        namespaced.values = inserted_entry(
            namespaced.values,
            ConfigNode::Str(key.to_owned()),
            expanded?,
        );
        namespaced.replaced.push(key);
    }
    Ok(namespaced)
}
