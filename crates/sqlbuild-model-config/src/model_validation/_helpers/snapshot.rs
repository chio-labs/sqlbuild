//! `validate_snapshot_config`, raising the first error the Python validator raises.

use crate::model_validation::_helpers::config::{
    ConfigView, has_config_value, one_of, same_lowered, sorted_values, string_sequence,
};
use crate::model_validation::_helpers::incremental::{contract_declared_columns, require_declared};
use crate::model_validation::constants::{
    APPEND_NEW_COLUMNS_POLICY, CHANGES_HISTORICAL_INPUT, CHECK_SNAPSHOT_STRATEGY,
    CONTRACT_SCHEMA_CHANGE_CODE, ENFORCED_CONTRACT, HISTORICAL_INPUTS, INITIAL_VALID_FROM_VALUES,
    SNAPSHOT_DISALLOWED_KEYS, SNAPSHOT_FULL_REFRESH_POLICIES, SNAPSHOT_MATERIALIZATION,
    SNAPSHOT_SCHEMA_CHANGE_POLICIES, SNAPSHOT_STRATEGIES, SQL_WILDCARD,
    TIMESTAMP_SNAPSHOT_STRATEGY,
};
use crate::model_validation::models::{ModelValidationFacts, ValidationStop};
use crate::model_validation::types::Check;
use crate::types::{AuthoredNode, NodeKind};

const UPDATED_AT: &str = "updated_at";
const OBSERVED_AT: &str = "observed_at";

/// The snapshot config values `validate_snapshot_config` reads, in its order.
struct SnapshotValues<N> {
    strategy: Option<String>,
    updated_at: Option<String>,
    observed_at: Option<String>,
    historical_input: Option<String>,
    initial_valid_from: Option<String>,
    full_refresh: Option<String>,
    schema_change: Option<String>,
    unique_key: Option<N>,
    check_columns: Option<N>,
    valid_from_column: Option<String>,
    valid_to_column: Option<String>,
}

impl<N: AuthoredNode> SnapshotValues<N> {
    fn read(config: &ConfigView<'_, N>) -> Result<Self, ValidationStop> {
        let strategy = config.string("snapshot_strategy")?;
        let updated_at = config.string(UPDATED_AT)?;
        let observed_at = config.string(OBSERVED_AT)?;
        let historical_input = config.string("historical_input")?;
        let initial_valid_from = config.string("initial_valid_from")?;
        let full_refresh = config.string("snapshot_full_refresh")?;
        let schema_change = config.string("snapshot_schema_change")?;
        let unique_key = config.get("unique_key").cloned();
        let check_columns = config.get("check_columns").cloned();
        let valid_from_column = config.string("valid_from_column")?;
        let valid_to_column = config.string("valid_to_column")?;
        Ok(Self {
            strategy,
            updated_at,
            observed_at,
            historical_input,
            initial_valid_from,
            full_refresh,
            schema_change,
            unique_key,
            check_columns,
            valid_from_column,
            valid_to_column,
        })
    }
}

/// Check the snapshot rules for one model's layered config.
pub(crate) fn check_snapshot<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    if config.string("materialized")?.as_deref() != Some(SNAPSHOT_MATERIALIZATION) {
        return Ok(());
    }
    let values = SnapshotValues::read(config)?;
    if let Some(key) = config.first_present(&SNAPSHOT_DISALLOWED_KEYS) {
        return Err(config.error(format!("{key} is not allowed on snapshot models")));
    }
    check_strategy(config, &values)?;
    check_history(config, &values)?;
    check_policies(config, &values)?;
    if let (Some(valid_from), Some(valid_to)) = (&values.valid_from_column, &values.valid_to_column)
        && same_lowered(valid_from, valid_to)?
    {
        return Err(config.error("valid_from_column and valid_to_column must differ"));
    }
    check_contract_columns(config, &values, facts)
}

fn check_strategy<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    values: &SnapshotValues<N>,
) -> Check {
    if !has_config_value(values.unique_key.as_ref()) {
        return Err(config.error("snapshot materialization requires unique_key"));
    }
    let Some(strategy) = values.strategy.as_deref() else {
        return Err(config.error("snapshot materialization requires snapshot_strategy"));
    };
    if !one_of(strategy, &SNAPSHOT_STRATEGIES) {
        return Err(config.error(format!(
            "unknown snapshot_strategy '{strategy}'; valid values: {}",
            sorted_values(&SNAPSHOT_STRATEGIES)
        )));
    }
    if strategy == TIMESTAMP_SNAPSHOT_STRATEGY && values.updated_at.is_none() {
        return Err(config.error("snapshot_strategy=timestamp requires updated_at"));
    }
    let check = strategy == CHECK_SNAPSHOT_STRATEGY;
    if check && !has_config_value(values.check_columns.as_ref()) {
        return Err(config.error("snapshot_strategy=check requires check_columns"));
    }
    if check && values.check_columns.as_ref().is_some_and(mixes_wildcard) {
        return Err(config.error("check_columns [*] cannot be combined with explicit columns"));
    }
    Ok(())
}

fn check_history<N: AuthoredNode>(config: &ConfigView<'_, N>, values: &SnapshotValues<N>) -> Check {
    let historical_input = values.historical_input.as_deref();
    let strategy = values.strategy.as_deref();
    if historical_input.is_some() && values.observed_at.is_none() {
        return Err(config.error("historical_input requires observed_at"));
    }
    if let Some(historical_input) = historical_input
        && !one_of(historical_input, &HISTORICAL_INPUTS)
    {
        return Err(config.error(format!(
            "unknown historical_input '{historical_input}'; valid values: {}",
            sorted_values(&HISTORICAL_INPUTS)
        )));
    }
    if values.observed_at.is_some()
        && strategy == Some(TIMESTAMP_SNAPSHOT_STRATEGY)
        && historical_input.is_none()
    {
        return Err(config.error(
            "timestamp snapshots with observed_at require historical_input snapshot or changes",
        ));
    }
    let changes = historical_input == Some(CHANGES_HISTORICAL_INPUT);
    if strategy == Some(CHECK_SNAPSHOT_STRATEGY) && changes {
        return Err(
            config.error("historical_input=changes is not valid with snapshot_strategy=check")
        );
    }
    match config
        .get("invalidate_hard_deletes")
        .map(AuthoredNode::kind)
    {
        None | Some(NodeKind::Bool(false)) => Ok(()),
        Some(NodeKind::Bool(true)) if !changes => Ok(()),
        Some(NodeKind::Bool(true)) => {
            Err(config.error("invalidate_hard_deletes is not valid with historical_input=changes"))
        }
        Some(_) => Err(config.error("invalidate_hard_deletes must be a boolean")),
    }
}

fn check_policies<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    values: &SnapshotValues<N>,
) -> Check {
    let initial_valid_from = values.initial_valid_from.as_deref();
    if let Some(initial) = initial_valid_from
        && !one_of(initial, &INITIAL_VALID_FROM_VALUES)
    {
        return Err(config.error(format!(
            "unknown initial_valid_from '{initial}'; valid values: {}",
            sorted_values(&INITIAL_VALID_FROM_VALUES)
        )));
    }
    if initial_valid_from == Some(UPDATED_AT) && values.updated_at.is_none() {
        return Err(config.error("initial_valid_from=updated_at requires updated_at"));
    }
    if initial_valid_from == Some(OBSERVED_AT) && values.observed_at.is_none() {
        return Err(config.error("initial_valid_from=observed_at requires observed_at"));
    }
    if let Some(full_refresh) = values.full_refresh.as_deref()
        && !one_of(full_refresh, &SNAPSHOT_FULL_REFRESH_POLICIES)
    {
        return Err(config.error(format!(
            "unknown snapshot_full_refresh '{full_refresh}'; valid values: {}",
            sorted_values(&SNAPSHOT_FULL_REFRESH_POLICIES)
        )));
    }
    let Some(schema_change) = values.schema_change.as_deref() else {
        return Ok(());
    };
    if !one_of(schema_change, &SNAPSHOT_SCHEMA_CHANGE_POLICIES) {
        return Err(config.error(format!(
            "unknown snapshot_schema_change '{schema_change}'; valid values: {}",
            sorted_values(&SNAPSHOT_SCHEMA_CHANGE_POLICIES)
        )));
    }
    if config.equals("contract", ENFORCED_CONTRACT) && schema_change == APPEND_NEW_COLUMNS_POLICY {
        return Err(ValidationStop::Error(
            config
                .config_error(
                    "snapshot_schema_change=append_new_columns is not valid with contract \
                     enforced; add new columns to the contract or set contract none",
                )
                .with_code(CONTRACT_SCHEMA_CHANGE_CODE),
        ));
    }
    Ok(())
}

fn check_contract_columns<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    values: &SnapshotValues<N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    let Some(declared) = contract_declared_columns(config, facts) else {
        return Ok(());
    };
    require_declared(
        config,
        "unique_key",
        &string_sequence(values.unique_key.as_ref())?,
        &declared,
    )?;
    if let Some(updated_at) = &values.updated_at {
        require_declared(
            config,
            UPDATED_AT,
            std::slice::from_ref(updated_at),
            &declared,
        )?;
    }
    if let Some(observed_at) = &values.observed_at {
        require_declared(
            config,
            OBSERVED_AT,
            std::slice::from_ref(observed_at),
            &declared,
        )?;
    }
    if values.check_columns.as_ref().is_some_and(is_wildcard_only) {
        return Ok(());
    }
    require_declared(
        config,
        "check_columns",
        &string_sequence(values.check_columns.as_ref())?,
        &declared,
    )
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
