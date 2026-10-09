//! Python's managed source and seed targets (`assembly/project.py`, `assembly/targets.py`).

use crate::assembly::project::_helpers::templates::{Context, TemplateInputs, expanded_text};
use crate::assembly::project::constants::{
    DESTINATION_DATABASE_CONTEXT, DESTINATION_QUALIFIED_CONTEXT, DESTINATION_SCHEMA_CONTEXT,
    DESTINATION_TABLE_CONTEXT, MODEL_ALIAS_CONTEXT, MODEL_DATABASE_CONTEXT, MODEL_NAME_CONTEXT,
    MODEL_SCHEMA_CONTEXT, PRESERVE_TARGET_VALUE, PRESERVED_NAMESPACE_DEFERRAL,
};
use crate::assembly::project::models::{
    Namespace, SeedDefaults, SeedFacts, SourceFacts, TargetNamespace,
};
use crate::assembly::project::types::Fact;

/// A managed source's `(database, schema)`.
pub(crate) type SourceNamespace = (Option<String>, Option<String>);

/// `_build_source_relation_entry`: None where the entry stays as authored.
pub(crate) fn managed_source(
    source: &SourceFacts,
    target: Option<&TargetNamespace>,
    inputs: &TemplateInputs<'_>,
) -> Fact<Option<SourceNamespace>> {
    let Some(target) = target.filter(|_| source.managed) else {
        return Ok(None);
    };
    let loader_schema: Option<&String> =
        python_or(target.loader_schema.as_ref(), target.schema.as_ref());
    let loader_target = TargetNamespace {
        database: target.database.clone(),
        schema: loader_schema.cloned(),
        loader_schema: target.loader_schema.clone(),
    };
    preserved_namespace(
        Some(&loader_target),
        source.database.as_ref(),
        source.schema.as_ref(),
    )?;
    let database: Option<String> = match &source.database {
        Some(database) => Some(database.clone()),
        None => optional_text(target.database.as_deref(), inputs)?,
    };
    let schema: Option<String> = match &source.schema {
        Some(schema) => Some(schema.clone()),
        None => optional_text(loader_schema.map(String::as_str), inputs)?,
    };
    Ok(Some((database, schema)))
}

/// `build_seed_relation_target`.
pub(crate) fn seed_target(
    seed: &SeedFacts,
    defaults: &SeedDefaults,
    target: Option<&TargetNamespace>,
    inputs: &TemplateInputs<'_>,
) -> Fact<Namespace> {
    let mut logical_database: Option<String> = environment_text(
        defaults
            .seed_database
            .as_ref()
            .or(defaults.database.as_ref()),
        inputs,
    )?;
    let mut logical_schema: Option<String> = environment_text(
        defaults.seed_schema.as_ref().or(defaults.schema.as_ref()),
        inputs,
    )?;
    if let Some(raw) = &seed.database {
        let context = seed_context(&seed.name, logical_database.clone(), logical_schema.clone());
        logical_database = seed_text(raw, inputs, &context)?;
    }
    if let Some(raw) = &seed.schema {
        let context = seed_context(&seed.name, logical_database.clone(), logical_schema.clone());
        logical_schema = seed_text(raw, inputs, &context)?;
    }
    preserved_namespace(target, logical_database.as_ref(), logical_schema.as_ref())?;
    let (database, schema) = match target {
        None => (logical_database.clone(), logical_schema.clone()),
        Some(target) => (
            target_override(target.database.as_ref(), logical_database.clone(), inputs)?,
            target_override(target.schema.as_ref(), logical_schema.clone(), inputs)?,
        ),
    };
    Ok(Namespace {
        database,
        schema,
        logical_database,
        logical_schema,
    })
}

/// `validate_preserved_logical_namespace`; Python raises where Err.
fn preserved_namespace(
    target: Option<&TargetNamespace>,
    logical_database: Option<&String>,
    logical_schema: Option<&String>,
) -> Fact<()> {
    let Some(target) = target else {
        return Ok(());
    };
    let preserved =
        |value: Option<&String>| value.is_some_and(|value| value == PRESERVE_TARGET_VALUE);
    if (preserved(target.database.as_ref()) && logical_database.is_none())
        || (preserved(target.schema.as_ref()) && logical_schema.is_none())
    {
        return Err(PRESERVED_NAMESPACE_DEFERRAL.to_owned());
    }
    Ok(())
}

/// `_expand_target_value`.
fn optional_text(value: Option<&str>, inputs: &TemplateInputs<'_>) -> Fact<Option<String>> {
    value
        .map(|value| expanded_text(value, inputs, None))
        .transpose()
}

/// `_expand_seed_default_value` and `_expand_seed_environment_value`.
fn environment_text(raw: Option<&String>, inputs: &TemplateInputs<'_>) -> Fact<Option<String>> {
    match raw {
        None => Ok(None),
        Some(raw) if raw == PRESERVE_TARGET_VALUE => Ok(None),
        Some(raw) => expanded_text(raw, inputs, None).map(Some),
    }
}

/// `_expand_seed_target_value`.
fn seed_text(
    raw: &str,
    inputs: &TemplateInputs<'_>,
    context: &Context<'_>,
) -> Fact<Option<String>> {
    if raw == PRESERVE_TARGET_VALUE {
        return Ok(None);
    }
    expanded_text(raw, inputs, Some(context)).map(Some)
}

/// `_apply_seed_target_overrides` for one dimension.
fn target_override(
    raw: Option<&String>,
    logical: Option<String>,
    inputs: &TemplateInputs<'_>,
) -> Fact<Option<String>> {
    match raw {
        Some(raw) if raw != PRESERVE_TARGET_VALUE => environment_text(Some(raw), inputs),
        _ => Ok(logical),
    }
}

/// The context values a seed's own database and schema templates read.
fn seed_context(
    name: &str,
    database: Option<String>,
    schema: Option<String>,
) -> Vec<(&'static str, Option<String>)> {
    let qualified: Option<String> = match (&database, &schema) {
        (Some(database), Some(schema)) => Some(format!("{database}.{schema}.{name}")),
        (None, Some(schema)) => Some(format!("{schema}.{name}")),
        _ => None,
    };
    vec![
        (MODEL_NAME_CONTEXT, Some(name.to_owned())),
        (MODEL_DATABASE_CONTEXT, database.clone()),
        (MODEL_SCHEMA_CONTEXT, schema.clone()),
        (MODEL_ALIAS_CONTEXT, Some(name.to_owned())),
        (DESTINATION_DATABASE_CONTEXT, database),
        (DESTINATION_SCHEMA_CONTEXT, schema),
        (DESTINATION_TABLE_CONTEXT, Some(name.to_owned())),
        (DESTINATION_QUALIFIED_CONTEXT, qualified),
    ]
}

/// Python's `left or right` over optional text: an empty string falls through.
fn python_or<'a>(left: Option<&'a String>, right: Option<&'a String>) -> Option<&'a String> {
    left.filter(|value| !value.is_empty()).or(right)
}
