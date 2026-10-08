//! Contract, materialization, storage, migration and placeholder rules Python certainly accepts.

use std::collections::BTreeSet;

use crate::model_validation::_helpers::config::{ConfigView, one_of, string_value};
use crate::model_validation::_helpers::durations::parse_duration;
use crate::model_validation::_helpers::text::{python_lower, python_strip};
use crate::model_validation::constants::{
    BUILTIN_MATERIALIZATIONS, CONTRACT_POLICIES, CUSTOM_MATERIALIZATION_DISALLOWED_KEYS,
    HISTORY_MATERIALIZATIONS, INCREMENTAL_MATERIALIZATION, INCREMENTAL_ONLY_KEYS,
    OLD_NAME_VIEW_KEY, PLACEHOLDER_SIGIL, TABLE_BACKED_MATERIALIZATIONS, VIEW_MATERIALIZATION,
};
use crate::model_validation::models::{ModelValidationFacts, ProjectValidationFacts, Rejected};
use crate::model_validation::types::Check;
use crate::types::{AuthoredNode, NodeKind};

const MIGRATE_FROM_KEY: &str = "migrate_from";
const MIGRATE_FORCE_KEY: &str = "migrate_force";

/// Accept `validate_microbatch_project_capability`.
pub(crate) fn check_project_capability<N: AuthoredNode>(
    config: &ConfigView<N>,
    project: &ProjectValidationFacts,
) -> Check {
    let Some(concurrency) = config.get("batch_concurrency") else {
        return Ok(());
    };
    match (concurrency.kind(), concurrency.integer()) {
        (NodeKind::Int { .. }, Some(value)) if value > 1 && !project.microbatch_concurrency => {
            Err(Rejected)
        }
        (NodeKind::Int { .. }, None) => Err(Rejected),
        _ => Ok(()),
    }
}

/// Accept `validate_contract_config` and `validate_non_incremental_config`.
pub(crate) fn check_contract_and_incremental_keys<N: AuthoredNode>(
    config: &ConfigView<N>,
) -> Check {
    if let Some(contract) = config.get("contract")
        && !one_of(&string_value(contract)?, &CONTRACT_POLICIES)
    {
        return Err(Rejected);
    }
    if config.string("materialized")?.as_deref() != Some(INCREMENTAL_MATERIALIZATION)
        && config.any_present(&INCREMENTAL_ONLY_KEYS)
    {
        return Err(Rejected);
    }
    Ok(())
}

/// Accept `validate_custom_materialization_config`.
pub(crate) fn check_custom_materialization<N: AuthoredNode>(
    config: &ConfigView<N>,
    project: &ProjectValidationFacts,
) -> Check {
    let Some(materialized) = config.string("materialized")? else {
        return Ok(());
    };
    if one_of(&materialized, &BUILTIN_MATERIALIZATIONS) {
        return Ok(());
    }
    if !project.custom_materializations.contains(&materialized)
        || config.any_present(&CUSTOM_MATERIALIZATION_DISALLOWED_KEYS)
    {
        return Err(Rejected);
    }
    Ok(())
}

/// Accept `validate_storage_policies`.
pub(crate) fn check_storage_policies<N: AuthoredNode>(
    config: &ConfigView<N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    if facts.retention_unmanaged && !facts.table_type_declared {
        return Ok(());
    }
    let materialized = config.string("materialized")?;
    match materialized.as_deref() {
        Some(VIEW_MATERIALIZATION) | None => Err(Rejected),
        Some(value) if one_of(value, &TABLE_BACKED_MATERIALIZATIONS) => Ok(()),
        Some(_) => Err(Rejected),
    }
}

/// Accept `validate_model_migration_config`.
pub(crate) fn check_migration<N: AuthoredNode>(
    config: &ConfigView<N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    if config.contains_key(OLD_NAME_VIEW_KEY) {
        let value = config.get(OLD_NAME_VIEW_KEY).ok_or(Rejected)?;
        if value.kind() != NodeKind::Bool(false) {
            let text = string_value(value)?;
            if parse_duration(python_strip(&text)?)?.is_none() {
                return Err(Rejected);
            }
        }
    }
    let migrate_from = config.get(MIGRATE_FROM_KEY);
    let migrate_force = config.get(MIGRATE_FORCE_KEY);
    if migrate_from.is_none() && migrate_force.is_none() {
        return Ok(());
    }
    let materialized = config.string("materialized")?.ok_or(Rejected)?;
    if !one_of(&materialized, &TABLE_BACKED_MATERIALIZATIONS)
        && materialized != VIEW_MATERIALIZATION
    {
        return Err(Rejected);
    }
    if migrate_force.is_some() && !one_of(&materialized, &HISTORY_MATERIALIZATIONS) {
        return Err(Rejected);
    }
    let origin = string_value(migrate_from.ok_or(Rejected)?)?;
    let origin = python_strip(&origin)?;
    if origin.is_empty() || python_lower(origin)? == python_lower(facts.model_name)? {
        return Err(Rejected);
    }
    match migrate_force.map(AuthoredNode::kind) {
        None | Some(NodeKind::Bool(_)) => Ok(()),
        Some(_) => Err(Rejected),
    }
}

/// Accept `validate_placeholder_config`.
pub(crate) fn check_placeholders<N: AuthoredNode>(
    config: &ConfigView<N>,
    project: &ProjectValidationFacts,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    let materialized = config.string("materialized")?;
    let custom = materialized
        .as_ref()
        .is_some_and(|value| project.custom_materializations.contains(value));
    let used = placeholder_names(facts.query_sql)?;
    let declared = config.get("placeholders");
    if !custom {
        return if used.is_empty() && declared.is_none() {
            Ok(())
        } else {
            Err(Rejected)
        };
    }
    let declared_names = match declared {
        Some(value) if value.kind() == NodeKind::Map => value
            .entries()
            .iter()
            .map(|(key, _)| string_value(key))
            .collect::<Result<BTreeSet<_>, _>>()?,
        _ => BTreeSet::new(),
    };
    if declared_names == used {
        Ok(())
    } else {
        Err(Rejected)
    }
}

/// Return the names `re.findall(r"@@@(\w+)", sql)` finds, rejecting non-ASCII word candidates.
fn placeholder_names(sql: &str) -> Result<BTreeSet<String>, Rejected> {
    let mut names: BTreeSet<String> = BTreeSet::new();
    let mut rest = sql;
    while let Some(start) = rest.find(PLACEHOLDER_SIGIL) {
        let after = &rest[start + PLACEHOLDER_SIGIL.len()..];
        let length = after
            .bytes()
            .take_while(|byte| byte.is_ascii_alphanumeric() || *byte == b'_')
            .count();
        if after[length..]
            .chars()
            .next()
            .is_some_and(|next| !next.is_ascii())
        {
            return Err(Rejected);
        }
        if length == 0 {
            rest = &rest[start + 1..];
            continue;
        }
        names.insert(after[..length].to_owned());
        rest = &after[length..];
    }
    Ok(names)
}
