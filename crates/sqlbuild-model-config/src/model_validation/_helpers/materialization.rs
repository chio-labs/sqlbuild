//! Contract, materialization, storage, migration and placeholder rules with Python's errors.

use crate::execution_limits::constants::MODEL_MAX_DURATION_KEY;
use crate::execution_limits::main::parse_execution_limit::parse_execution_limit;
use std::collections::{BTreeSet, HashMap};

use sqlbuild_core::text::main::is_word_char::is_word_char;

use crate::errors::ConfigError;
use crate::model_validation::_helpers::config::python_lower;
use crate::model_validation::_helpers::config::{
    ConfigView, one_of, sorted_values, text_if_string,
};
use crate::model_validation::constants::{
    BUILTIN_MATERIALIZATIONS, CONTRACT_POLICIES, CUSTOM_MATERIALIZATION_DISALLOWED_KEYS,
    HISTORY_MATERIALIZATIONS, INCREMENTAL_MATERIALIZATION, INCREMENTAL_ONLY_KEYS,
    MICROBATCH_CONCURRENCY_HELP, MICROBATCH_CONCURRENCY_NOTE, OLD_NAME_VIEW_KEY, PLACEHOLDER_SIGIL,
    TABLE_BACKED_MATERIALIZATIONS, VIEW_MATERIALIZATION,
};
use crate::model_validation::constants::{
    CHAINED_HELP, CLAIMED_HELP, MATERIALIZATION_HELP, MIGRATABLE_MATERIALIZATIONS, ORIGIN_HELP,
    QUALIFIED_NAME_SEPARATOR,
};
use crate::model_validation::models::{
    ModelValidationFacts, ProjectValidationFacts, ValidationStop,
};
use crate::model_validation::types::Check;
use crate::types::{AuthoredNode, NodeKind};

const MIGRATE_FROM_KEY: &str = "migrate_from";
const MIGRATE_FORCE_KEY: &str = "migrate_force";

/// Check `validate_microbatch_project_capability`.
pub(crate) fn check_project_capability<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    project: &ProjectValidationFacts,
) -> Check {
    let Some(concurrency) = config.get("batch_concurrency") else {
        return Ok(());
    };
    let concurrent = match (concurrency.kind(), concurrency.integer()) {
        (NodeKind::Int { negative: false }, Some(value)) => value > 1,
        (NodeKind::Int { negative: false }, None) => true,
        _ => false,
    };
    if concurrent && !project.microbatch_concurrency {
        return Err(ValidationStop::Error(
            config
                .config_error(format!(
                    "batch_concurrency > 1 requires concurrent microbatches; \
                     {MICROBATCH_CONCURRENCY_NOTE}"
                ))
                .with_help(MICROBATCH_CONCURRENCY_HELP),
        ));
    }
    Ok(())
}

/// Check `validate_contract_config`.
pub(crate) fn check_contract<N: AuthoredNode>(config: &ConfigView<'_, N>) -> Check {
    let Some(contract) = config.get("contract") else {
        return Ok(());
    };
    if contract.kind() != NodeKind::Str {
        return Err(config.error("contract must be a string"));
    }
    if CONTRACT_POLICIES
        .iter()
        .any(|policy| contract.is_text(policy))
    {
        return Ok(());
    }
    let contract: String = contract.text().unwrap_or_default();
    Err(config.error(format!(
        "unknown contract '{contract}'; valid values: {}",
        sorted_values(&CONTRACT_POLICIES)
    )))
}

/// Check that `max_duration` is a positive fixed duration or `disabled`.
pub(crate) fn check_execution_limit<N: AuthoredNode>(config: &ConfigView<'_, N>) -> Check {
    let Some(text) = config.string(MODEL_MAX_DURATION_KEY)? else {
        return Ok(());
    };
    if parse_execution_limit(&text).is_some() {
        return Ok(());
    }
    Err(config.error(format!(
        "{MODEL_MAX_DURATION_KEY} must be a positive fixed duration such as '15m' or '1h', or \
         'disabled', got '{text}'"
    )))
}

/// Check `validate_non_incremental_config`.
pub(crate) fn check_non_incremental<N: AuthoredNode>(config: &ConfigView<'_, N>) -> Check {
    if config.string("materialized")?.as_deref() == Some(INCREMENTAL_MATERIALIZATION) {
        return Ok(());
    }
    match config.first_present(&INCREMENTAL_ONLY_KEYS) {
        Some(key) => Err(config.error(format!("{key} is only valid for incremental models"))),
        None => Ok(()),
    }
}

/// Check `validate_custom_materialization_config`.
pub(crate) fn check_custom_materialization<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    project: &ProjectValidationFacts,
) -> Check {
    let Some(materialized) = config.string("materialized")? else {
        return Ok(());
    };
    if one_of(&materialized, &BUILTIN_MATERIALIZATIONS) {
        return Ok(());
    }
    if !project.custom_materializations.contains(&materialized) {
        return Err(config.error(format!(
            "unknown materialization '{materialized}'; not a built-in type and no custom \
             materialization with that name was discovered"
        )));
    }
    match config.first_present(&CUSTOM_MATERIALIZATION_DISALLOWED_KEYS) {
        Some(key) => Err(config.error(format!("{key} is not allowed on custom materializations"))),
        None => Ok(()),
    }
}

/// Check `validate_storage_policies`.
pub(crate) fn check_storage_policies<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    let materialized = config.string("materialized")?;
    let materialized = materialized.as_deref();
    let shown = materialized.unwrap_or("None");
    let table_backed =
        materialized.is_some_and(|value| one_of(value, &TABLE_BACKED_MATERIALIZATIONS));
    if !facts.retention_unmanaged {
        if materialized == Some(VIEW_MATERIALIZATION) {
            return Err(config.error(
                "managed time_travel_retention is not valid for views; set \
                 time_travel_retention disabled",
            ));
        }
        if !table_backed {
            return Err(config.error(format!(
                "managed time_travel_retention is not supported for materialization '{shown}'"
            )));
        }
    }
    if facts.table_type_declared {
        if materialized == Some(VIEW_MATERIALIZATION) {
            return Err(config.error("table_type is not valid for views"));
        }
        if !table_backed {
            return Err(config.error(format!(
                "table_type is not supported for materialization '{shown}'"
            )));
        }
    }
    Ok(())
}

/// Check `validate_model_migration_config`.
pub(crate) fn check_migration<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    check_old_name_view(config)?;
    let migrate_from = config.get(MIGRATE_FROM_KEY);
    let migrate_force = config.get(MIGRATE_FORCE_KEY);
    if migrate_from.is_none() && migrate_force.is_none() {
        return Ok(());
    }
    let materialized = config.string("materialized")?;
    let migratable = materialized.as_deref().is_some_and(|value| {
        value == VIEW_MATERIALIZATION || one_of(value, &TABLE_BACKED_MATERIALIZATIONS)
    });
    if !migratable {
        return Err(config
            .error("migrate_from is only valid for table, view, incremental and snapshot models"));
    }
    let materialized = materialized.unwrap_or_default();
    if migrate_force.is_some() && !one_of(&materialized, &HISTORY_MATERIALIZATIONS) {
        return Err(ValidationStop::Error(
            config
                .config_error(format!(
                    "migrate_force is only valid for incremental and snapshot models; nothing is \
                     replaced when a '{materialized}' model migrates, because tables and views \
                     are rebuilt under their new name"
                ))
                .with_help("remove migrate_force from the model header"),
        ));
    }
    let Some(migrate_from) = migrate_from else {
        return Err(config.error("migrate_force requires migrate_from"));
    };
    let origin: String = text_if_string(migrate_from)
        .map(|text| str::trim(&text).to_owned())
        .unwrap_or_default();
    if origin.is_empty() {
        return Err(config.error("migrate_from must be a model name or a qualified relation"));
    }
    if python_lower(&origin) == python_lower(facts.model_name) {
        return Err(config.error("migrate_from cannot name the model itself"));
    }
    match migrate_force.map(AuthoredNode::kind) {
        None | Some(NodeKind::Bool(_)) => Ok(()),
        Some(_) => Err(config.error("migrate_force must be true or false")),
    }
}

fn check_old_name_view<N: AuthoredNode>(config: &ConfigView<'_, N>) -> Check {
    let Some(value) = config.raw(OLD_NAME_VIEW_KEY) else {
        return Ok(());
    };
    if value.kind() == NodeKind::Bool(false) {
        return Ok(());
    }
    if let Some(text) = text_if_string(value)
        && config
            .duration(OLD_NAME_VIEW_KEY, str::trim(&text))?
            .is_some()
    {
        return Ok(());
    }
    let shown: String = value.python_repr();
    Err(ValidationStop::Error(
        config
            .config_error(format!(
                "old_name_view must be a positive duration such as 7d, or false; got {shown}"
            ))
            .with_help("write for example old_name_view 7d, or old_name_view false"),
    ))
}

/// Check `validate_placeholder_config`.
pub(crate) fn check_placeholders<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    project: &ProjectValidationFacts,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    let materialized = config.string("materialized")?;
    let custom = materialized
        .as_ref()
        .is_some_and(|value| project.custom_materializations.contains(value));
    let used = placeholder_names(facts.query_sql);
    let declared = config.get("placeholders");
    if !custom && !used.is_empty() {
        return Err(config.error("@@@placeholders are only allowed on custom materializations"));
    }
    if !custom && declared.is_some() {
        return Err(config.error("placeholders config is only allowed on custom materializations"));
    }
    if !custom || (used.is_empty() && declared.is_none()) {
        return Ok(());
    }
    let declared_names = match declared {
        Some(value) if value.kind() == NodeKind::Map => value
            .entries()
            .iter()
            .map(|(key, _)| key.python_str())
            .collect::<BTreeSet<String>>(),
        _ => BTreeSet::new(),
    };
    let missing: Vec<&str> = used
        .difference(&declared_names)
        .map(String::as_str)
        .collect();
    if !missing.is_empty() {
        return Err(config.error(format!(
            "@@@placeholders without default values in placeholders config: {}",
            missing.join(", ")
        )));
    }
    let unused: Vec<&str> = declared_names
        .difference(&used)
        .map(String::as_str)
        .collect();
    if !unused.is_empty() {
        return Err(config.error(format!(
            "placeholders config entries not used in SQL: {}",
            unused.join(", ")
        )));
    }
    Ok(())
}

/// Return the names `re.findall(r"@@@(\w+)", sql)` finds; `\w` is Python's word class.
fn placeholder_names(sql: &str) -> BTreeSet<String> {
    let mut names: BTreeSet<String> = BTreeSet::new();
    let mut rest = sql;
    while let Some(start) = rest.find(PLACEHOLDER_SIGIL) {
        let after = &rest[start + PLACEHOLDER_SIGIL.len()..];
        let length: usize = after
            .char_indices()
            .find(|(_, character)| !is_word_char(*character))
            .map_or(after.len(), |(at, _)| at);
        if length == 0 {
            rest = &rest[start + 1..];
            continue;
        }
        names.insert(after[..length].to_owned());
        rest = &after[length..];
    }
    names
}

/// Column renames need a history model, or a table or view that migrates itself.
pub(crate) fn column_materialization_problem(
    model_name: &str,
    materialized: Option<&str>,
    model_migrates: bool,
    first: &str,
) -> Result<(), ConfigError> {
    let history: bool = materialized.is_some_and(|value| HISTORY_MATERIALIZATIONS.contains(&value));
    let migratable: bool =
        materialized.is_some_and(|value| MIGRATABLE_MATERIALIZATIONS.contains(&value));
    if !history && (!migratable || !model_migrates) {
        let shown: &str = materialized.unwrap_or("None");
        return Err(ConfigError::compile(format!(
            "model '{model_name}': column '{first}' declares migrate_from, which is only valid \
             for incremental and snapshot models, or for table and view models that declare \
             migrate_from themselves (the old name's compatibility view then presents the column \
             under its old name); '{shown}' models are rebuilt with their new columns"
        ))
        .with_help(MATERIALIZATION_HELP));
    }
    Ok(())
}

/// Each origin names one other column, claimed by only one rename.
pub(crate) fn origin_problem(
    model_name: &str,
    declared: &[(&str, &str)],
) -> Result<(), ConfigError> {
    let mut sources: HashMap<String, &str> = HashMap::new();
    for &(name, origin) in declared {
        let origin: &str = str::trim(origin);
        if origin.is_empty() || origin.contains(QUALIFIED_NAME_SEPARATOR) {
            return Err(ConfigError::compile(format!(
                "model '{model_name}': column '{name}' migrate_from must name one column of the \
                 model's existing table"
            ))
            .with_help(ORIGIN_HELP));
        }
        if python_lower(origin) == python_lower(name) {
            return Err(ConfigError::compile(format!(
                "model '{model_name}': column '{name}' migrate_from cannot name the column itself"
            )));
        }
        if let Some(claimed_by) = sources.get(&python_lower(origin)) {
            return Err(ConfigError::compile(format!(
                "model '{model_name}': columns '{claimed_by}' and '{name}' both declare \
                 migrate_from {origin}; a column can be renamed to only one new name"
            ))
            .with_help(CLAIMED_HELP));
        }
        sources.insert(python_lower(origin), name);
    }
    Ok(())
}

/// No rename may start from another renamed column.
pub(crate) fn chained_problem(
    model_name: &str,
    declared: &[(&str, &str)],
) -> Result<(), ConfigError> {
    let destinations: HashMap<String, &str> = declared
        .iter()
        .map(|&(name, _)| (python_lower(name), name))
        .collect();
    for &(name, origin) in declared {
        if destinations.contains_key(&python_lower(str::trim(origin))) {
            return Err(ConfigError::compile(format!(
                "model '{model_name}': column '{name}' migrates from '{origin}', which itself \
                 declares migrate_from; chained or swapped column renames are not supported"
            ))
            .with_help(CHAINED_HELP));
        }
    }
    Ok(())
}
