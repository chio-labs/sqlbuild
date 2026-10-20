//! The phases of one model's config build: layering, model templates, target namespace, result.

use crate::config_presence::main::contains_template::contains_template;
use crate::config_values::main::config_entry::config_entry;
use crate::config_values::main::inserted_entry::inserted_entry;
use crate::config_values::models::ConfigNode;
use crate::model_config_build::_helpers::checks::{
    check_hooks, check_no_config_macros, key_text, own_facts,
};
use crate::model_config_build::_helpers::context::{model_context, run_context, string_entry};
use crate::model_config_build::_helpers::expansion::{ExpansionSources, expand_entries};
use crate::model_config_build::_helpers::layers::{
    Entries, kept_own, layered_own, path_default_values, project_defaults,
};
use crate::model_config_build::_helpers::namespace::{Namespaced, namespaced_values};
use crate::model_config_build::_helpers::storage::{sorted_header_keys, storage_free_values};
use crate::model_config_build::constants::{
    DATABASE_KEY, HOOK_KEYS, MODEL_CONFIG_LABEL, RETENTION_KEY, SCHEMA_KEY, TABLE_TYPE_KEY,
};
use crate::model_config_build::models::{
    BuiltModelConfig, ConfigBuildHalt, ConfigBuildInputs, ModelHeader,
};
use crate::model_config_build::types::{ConfigBuildHost, HostEntries, HostHalt, HostNode};
use crate::model_validation::main::retention_override::retention_override;
use crate::model_validation::main::table_type_override::table_type_override;
use crate::types::AuthoredNode;

/// What one model's build reads: its host and project inputs, its header and its name.
pub(crate) struct BuildModel<'a, B: ConfigBuildHost> {
    pub(crate) host: &'a B,
    pub(crate) inputs: &'a ConfigBuildInputs<B::Handle>,
    pub(crate) header: ModelHeader<'a, B::Handle>,
    pub(crate) name: &'a str,
}

/// The values so far, the header keys still holding the header's own values, and the reads made.
pub(crate) struct Phase<H> {
    pub(crate) values: Entries<H>,
    pub(crate) own: Vec<String>,
    pub(crate) reads: Vec<(&'static str, String)>,
}

/// What layering sets aside until the end: hooks, which of them are the header's own, and the schema layer.
pub(crate) struct SetAside<H> {
    pub(crate) hooks: Entries<H>,
    pub(crate) own_hooks: Vec<String>,
    pub(crate) layer_schema_configured: bool,
}

/// The layered values, what is set aside, and whether any value holds a template.
pub(crate) struct Layered<H> {
    pub(crate) phase: Phase<H>,
    pub(crate) set_aside: SetAside<H>,
    pub(crate) has_templates: bool,
}

/// The namespaced values and the logical database and schema the model set itself.
pub(crate) struct Targeted<H> {
    pub(crate) phase: Phase<H>,
    pub(crate) logical_schema: Option<ConfigNode<H>>,
    pub(crate) logical_database: Option<ConfigNode<H>>,
}

/// The project defaults, the matched path default and the header merged, with hooks set aside.
pub(crate) fn layered<B: ConfigBuildHost>(
    model: &BuildModel<'_, B>,
    matched_path_default: Option<&str>,
) -> Result<Layered<B::Handle>, HostHalt<B>> {
    let path_values: Option<&Entries<B::Handle>> = matched_path_default
        .map(|key| path_default_values(model.inputs, key))
        .transpose()?;
    let mut defaults: Entries<B::Handle> = project_defaults(model.inputs);
    if let Some(path_values) = path_values {
        defaults = layered_own(model.host, &defaults, path_values)?.0;
    }
    let (mut values, own) = layered_own(model.host, &defaults, model.header.entries)?;
    check_hooks(model.host, &values, model.name)?;
    let mut hooks: Entries<B::Handle> = Vec::new();
    for key in HOOK_KEYS {
        if let Some(position) = values.iter().position(|(name, _)| name.is_text(key)) {
            hooks.push(values.remove(position));
        }
    }
    let has_templates: bool = values.iter().any(|(key, value)| {
        let facts = key_text(key).and_then(|name| own_facts(model.header.facts, &own, &name));
        facts.map_or_else(|| contains_template(&value), |facts| facts.template)
    });
    let own_hooks: Vec<String> = own
        .iter()
        .filter(|name| HOOK_KEYS.contains(&name.as_str()))
        .cloned()
        .collect();
    let layer_schema_configured: bool = config_entry(model.header.entries, SCHEMA_KEY).is_some()
        || path_values.is_some_and(|values| config_entry(values, SCHEMA_KEY).is_some());
    Ok(Layered {
        phase: Phase {
            values,
            own,
            reads: Vec::new(),
        },
        set_aside: SetAside {
            hooks,
            own_hooks,
            layer_schema_configured,
        },
        has_templates,
    })
}

/// `phase`'s values expanded once over `sources`, its reads extended.
fn expanded_phase<B: ConfigBuildHost>(
    mut phase: Phase<B::Handle>,
    sources: ExpansionSources<'_, B>,
    preserve_unknown_context: bool,
) -> Result<Phase<B::Handle>, HostHalt<B>> {
    let scope = (preserve_unknown_context, MODEL_CONFIG_LABEL);
    let (expanded, reads) = expand_entries(sources, &phase.values, scope);
    phase.reads.extend(reads);
    phase.values = expanded?;
    Ok(phase)
}

/// Sources of `model`'s host over `variables` and `context`.
fn sources<'a, B: ConfigBuildHost>(
    model: &BuildModel<'a, B>,
    variables: &'a [(HostNode<B>, HostNode<B>)],
    context: HostEntries<B>,
) -> ExpansionSources<'a, B> {
    ExpansionSources {
        host: model.host,
        variables,
        context,
    }
}

/// The model's templates expanded against the run, then twice against the model context.
pub(crate) fn model_templates<B: ConfigBuildHost>(
    model: &BuildModel<'_, B>,
    mut phase: Phase<B::Handle>,
) -> Result<Phase<B::Handle>, HostHalt<B>> {
    phase.own = kept_own(&phase.values, phase.own);
    let run = run_context(model.inputs);
    phase = expanded_phase(phase, sources(model, &model.inputs.variables, run), true)?;
    for _ in 0..2 {
        let context = model_context(model.inputs, &phase.values, model.name, false);
        phase = expanded_phase(phase, sources(model, &[], context), true)?;
    }
    Ok(phase)
}

/// The target's namespace applied, then target templates expanded when any are left.
pub(crate) fn targeted<B: ConfigBuildHost>(
    model: &BuildModel<'_, B>,
    mut phase: Phase<B::Handle>,
    has_templates: bool,
) -> Result<Targeted<B::Handle>, HostHalt<B>> {
    let logical_schema = string_entry(&phase.values, SCHEMA_KEY);
    let logical_database = string_entry(&phase.values, DATABASE_KEY);
    let logical = (logical_database.is_some(), logical_schema.is_some());
    let Namespaced {
        values,
        replaced,
        reads,
    } = namespaced_values(
        (model.host, model.inputs),
        &phase.values,
        logical,
        model.name,
    )?;
    phase.values = values;
    phase.reads.extend(reads);
    phase.own.retain(|name| !replaced.contains(&name.as_str()));
    let needs_target_templates: bool = has_templates
        || [DATABASE_KEY, SCHEMA_KEY].iter().any(|key| {
            config_entry(&phase.values, key).is_some_and(|value| contains_template(&value))
        });
    if needs_target_templates {
        phase.own = kept_own(&phase.values, phase.own);
        let context = model_context(model.inputs, &phase.values, model.name, true);
        phase = expanded_phase(phase, sources(model, &[], context), false)?;
    }
    Ok(Targeted {
        phase,
        logical_schema,
        logical_database,
    })
}

/// The built config: hooks restored, storage keys dropped, overrides read and macros rejected.
pub(crate) fn finished<B: ConfigBuildHost>(
    model: &BuildModel<'_, B>,
    set_aside: SetAside<B::Handle>,
    targeted: Targeted<B::Handle>,
) -> Result<BuiltModelConfig<B::Handle>, HostHalt<B>> {
    let SetAside {
        hooks,
        own_hooks,
        layer_schema_configured,
    } = set_aside;
    let (header, config) = (&model.header, ConfigBuildHalt::Config);
    let mut resolved: Entries<B::Handle> = targeted.phase.values;
    for (key, value) in hooks {
        resolved = inserted_entry(resolved, key, value);
    }
    let values: Entries<B::Handle> = storage_free_values(resolved, header.entries);
    let retention_value = config_entry(header.entries, RETENTION_KEY);
    let retention = retention_override(retention_value, model.name).map_err(config)?;
    let table_type_value = config_entry(header.entries, TABLE_TYPE_KEY);
    let table_type = table_type_override(table_type_value, model.name).map_err(config)?;
    check_no_config_macros(&values, header.facts, &targeted.phase.own).map_err(config)?;
    let mut own_header_keys: Vec<String> = targeted.phase.own;
    let restored: Vec<String> = own_hooks
        .into_iter()
        .filter(|name| !own_header_keys.contains(name))
        .collect();
    own_header_keys.extend(restored);
    Ok(BuiltModelConfig {
        values,
        header_keys: sorted_header_keys(header.entries)?,
        logical_schema: targeted.logical_schema,
        layer_schema_configured,
        logical_database: targeted.logical_database,
        retention,
        table_type,
        reads: targeted.phase.reads,
        own_header_keys,
    })
}
