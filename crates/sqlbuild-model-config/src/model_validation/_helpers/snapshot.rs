//! `validate_snapshot_config` for configs Python certainly accepts.

use crate::model_validation::_helpers::config::{
    ConfigView, has_config_value, one_of, string_sequence,
};
use crate::model_validation::_helpers::incremental::{contract_declared_columns, require_declared};
use crate::model_validation::_helpers::text::python_lower;
use crate::model_validation::constants::{
    APPEND_NEW_COLUMNS_POLICY, CHANGES_HISTORICAL_INPUT, CHECK_SNAPSHOT_STRATEGY,
    ENFORCED_CONTRACT, HISTORICAL_INPUTS, INITIAL_VALID_FROM_VALUES, SNAPSHOT_DISALLOWED_KEYS,
    SNAPSHOT_FULL_REFRESH_POLICIES, SNAPSHOT_MATERIALIZATION, SNAPSHOT_SCHEMA_CHANGE_POLICIES,
    SNAPSHOT_STRATEGIES, SQL_WILDCARD, TIMESTAMP_SNAPSHOT_STRATEGY,
};
use crate::model_validation::models::{ModelValidationFacts, Rejected};
use crate::model_validation::types::Check;
use crate::types::{AuthoredNode, NodeKind};

const UPDATED_AT: &str = "updated_at";
const OBSERVED_AT: &str = "observed_at";

/// Accept the snapshot rules for one model's layered config.
pub(crate) fn check_snapshot<N: AuthoredNode>(
    config: &ConfigView<N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    if config.string("materialized")?.as_deref() != Some(SNAPSHOT_MATERIALIZATION) {
        return Ok(());
    }
    let strategy = config.string("snapshot_strategy")?;
    let updated_at = config.string(UPDATED_AT)?;
    let observed_at = config.string(OBSERVED_AT)?;
    let historical_input = config.string("historical_input")?;
    let initial_valid_from = config.string("initial_valid_from")?;
    let full_refresh = config.string("snapshot_full_refresh")?;
    let schema_change = config.string("snapshot_schema_change")?;
    let valid_from_column = config.string("valid_from_column")?;
    let valid_to_column = config.string("valid_to_column")?;
    let unique_key = config.get("unique_key");
    let check_columns = config.get("check_columns");
    let strategy = strategy.as_deref();
    let historical_input = historical_input.as_deref();
    let changes = historical_input == Some(CHANGES_HISTORICAL_INPUT);
    let check = strategy == Some(CHECK_SNAPSHOT_STRATEGY);
    let timestamp = strategy == Some(TIMESTAMP_SNAPSHOT_STRATEGY);
    if config.any_present(&SNAPSHOT_DISALLOWED_KEYS)
        || !has_config_value(unique_key)
        || !strategy.is_some_and(|value| one_of(value, &SNAPSHOT_STRATEGIES))
        || (timestamp && updated_at.is_none())
        || (check && !has_config_value(check_columns))
        || (check && check_columns.is_some_and(mixes_wildcard))
        || (historical_input.is_some() && observed_at.is_none())
        || historical_input.is_some_and(|value| !one_of(value, &HISTORICAL_INPUTS))
        || (observed_at.is_some() && timestamp && historical_input.is_none())
        || (check && changes)
    {
        return Err(Rejected);
    }
    match config
        .get("invalidate_hard_deletes")
        .map(AuthoredNode::kind)
    {
        None | Some(NodeKind::Bool(false)) => {}
        Some(NodeKind::Bool(true)) if !changes => {}
        Some(_) => return Err(Rejected),
    }
    let initial_valid_from = initial_valid_from.as_deref();
    if initial_valid_from.is_some_and(|value| !one_of(value, &INITIAL_VALID_FROM_VALUES))
        || (initial_valid_from == Some(UPDATED_AT) && updated_at.is_none())
        || (initial_valid_from == Some(OBSERVED_AT) && observed_at.is_none())
        || full_refresh
            .as_deref()
            .is_some_and(|value| !one_of(value, &SNAPSHOT_FULL_REFRESH_POLICIES))
    {
        return Err(Rejected);
    }
    if let Some(schema_change) = schema_change.as_deref()
        && (!one_of(schema_change, &SNAPSHOT_SCHEMA_CHANGE_POLICIES)
            || (config.equals("contract", ENFORCED_CONTRACT)
                && schema_change == APPEND_NEW_COLUMNS_POLICY))
    {
        return Err(Rejected);
    }
    if let (Some(valid_from), Some(valid_to)) = (&valid_from_column, &valid_to_column)
        && python_lower(valid_from)? == python_lower(valid_to)?
    {
        return Err(Rejected);
    }
    let Some(declared) = contract_declared_columns(config, facts) else {
        return Ok(());
    };
    let checked_columns = if check_columns.is_some_and(is_wildcard_only) {
        Vec::new()
    } else {
        string_sequence(check_columns)?
    };
    let named = string_sequence(unique_key)?
        .into_iter()
        .chain(updated_at)
        .chain(observed_at)
        .chain(checked_columns);
    require_declared(named, &declared)
}

fn mixes_wildcard<N: AuthoredNode>(columns: &N) -> bool {
    if columns.kind() != NodeKind::List {
        return false;
    }
    let items = columns.items();
    items.len() != 1 && items.iter().any(|item| item.is_text(SQL_WILDCARD))
}

fn is_wildcard_only<N: AuthoredNode>(columns: &N) -> bool {
    columns.kind() == NodeKind::List
        && matches!(&columns.items()[..], [item] if item.is_text(SQL_WILDCARD))
}
