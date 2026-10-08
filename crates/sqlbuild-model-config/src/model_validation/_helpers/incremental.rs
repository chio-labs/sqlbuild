//! `validate_incremental_config` for configs Python certainly accepts.

use std::collections::HashSet;

use crate::model_validation::_helpers::config::{
    ConfigView, has_config_value, one_of, optional_one_of, reject_case_insensitive_duplicates,
    string_sequence, string_value,
};
use crate::model_validation::_helpers::cursor_bounds::{cursor_bound_key, keys_ordered};
use crate::model_validation::_helpers::durations::parse_duration;
use crate::model_validation::_helpers::microbatch::check_incremental_batching;
use crate::model_validation::_helpers::text::{python_lower, python_strip};
use crate::model_validation::constants::{
    APPEND_STRATEGY, BOUNDED_REPLAY_PREFIX, CURSOR_GRAIN_BATCH_SIZES, CURSOR_INPUT_KEYS,
    CURSOR_POLICY_DISABLED, CURSOR_TYPES, DELETE_INSERT_STRATEGY, EFFECTIVE_BATCH_SIZE,
    ENFORCED_CONTRACT, FUTURE_CURSOR_ACTIONS, INCREMENTAL_MATERIALIZATION, INCREMENTAL_STRATEGIES,
    MERGE_STRATEGY, ON_SCHEMA_CHANGE_POLICIES, REPLAY_ON_CHANGE_ACTIONS, TABLE_MATERIALIZATION,
    TIMESTAMP_CURSOR, VIEW_MATERIALIZATION, ZERO_DAY_DURATION,
};
use crate::model_validation::models::{ModelValidationFacts, Rejected};
use crate::model_validation::types::Check;
use crate::types::{AuthoredNode, NodeKind};

/// The incremental config values `_resolve_incremental_config_values` reads.
pub(crate) struct IncrementalValues<N> {
    pub(crate) strategy: Option<String>,
    pub(crate) cursor: Option<String>,
    pub(crate) cursor_type: Option<String>,
    pub(crate) cursor_grain: Option<String>,
    pub(crate) lookback: Option<String>,
    pub(crate) incremental_mode: Option<String>,
    pub(crate) batch_size: Option<String>,
    pub(crate) microbatch_strategy: Option<String>,
    pub(crate) cursor_watermark_mode: Option<String>,
    pub(crate) cursor_start: Option<N>,
    pub(crate) cursor_end: Option<N>,
    pub(crate) unique_key: Option<N>,
    pub(crate) cursor_inputs: Option<N>,
    pub(crate) max_microbatches: Option<N>,
    pub(crate) microbatch_limit: Option<N>,
    pub(crate) merge_exclude_columns: Option<N>,
}

impl<N: AuthoredNode> IncrementalValues<N> {
    fn read(config: &ConfigView<N>) -> Result<Self, Rejected> {
        let node = |key: &str| config.get(key).cloned();
        Ok(Self {
            strategy: config.string("incremental_strategy")?,
            cursor: config.string("cursor")?,
            cursor_type: config.string("cursor_type")?,
            cursor_grain: config.string("cursor_grain")?,
            lookback: config.string("lookback")?,
            incremental_mode: config.string("incremental_mode")?,
            batch_size: config.string("batch_size")?,
            microbatch_strategy: config.string("microbatch_strategy")?,
            cursor_watermark_mode: config.string("cursor_watermark_mode")?,
            cursor_start: node("cursor_start"),
            cursor_end: node("cursor_end"),
            unique_key: node("unique_key"),
            cursor_inputs: node("cursor_inputs"),
            max_microbatches: node("max_microbatches"),
            microbatch_limit: node("microbatch_limit"),
            merge_exclude_columns: node("merge_exclude_columns"),
        })
    }

    /// Return the `GRAIN_BATCH_SIZE` duration for an `effective` batch size, else the batch size.
    pub(crate) fn effective_batch_size(&self) -> Option<&str> {
        let batch_size = self.batch_size.as_deref()?;
        if batch_size != EFFECTIVE_BATCH_SIZE {
            return Some(batch_size);
        }
        let Some(grain) = self.cursor_grain.as_deref() else {
            return Some(batch_size);
        };
        CURSOR_GRAIN_BATCH_SIZES
            .iter()
            .find(|(name, _)| *name == grain)
            .map_or(Some(batch_size), |(_, size)| Some(size))
    }
}

/// Accept the incremental rules for one model's layered config.
pub(crate) fn check_incremental<N: AuthoredNode>(
    config: &ConfigView<N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    let materialized = config.string("materialized")?;
    let materialized = materialized.as_deref();
    if matches!(
        materialized,
        Some(TABLE_MATERIALIZATION | VIEW_MATERIALIZATION)
    ) && config.any_present(&CURSOR_INPUT_KEYS)
    {
        return Err(Rejected);
    }
    if materialized != Some(INCREMENTAL_MATERIALIZATION) {
        return Ok(());
    }
    let values = IncrementalValues::read(config)?;
    check_core(config, &values)?;
    check_incremental_batching(&values, config, facts)?;
    check_write_strategy(config, &values)?;
    check_contract_columns(config, &values, facts)?;
    if values.lookback.is_some() && values.cursor.is_none() {
        return Err(Rejected);
    }
    Ok(())
}

fn check_core<N: AuthoredNode>(config: &ConfigView<N>, values: &IncrementalValues<N>) -> Check {
    if let Some(value) = config.get("on_schema_change") {
        accept_text(value, |text| Ok(one_of(text, &ON_SCHEMA_CHANGE_POLICIES)))?;
    }
    if let Some(value) = config.get("replay_on_change") {
        accept_text(value, valid_replay_on_change)?;
    }
    if !optional_one_of(values.strategy.as_deref(), &INCREMENTAL_STRATEGIES) {
        return Err(Rejected);
    }
    check_cursor_rules(config, values)?;
    check_cursor_safety(config, values)
}

fn accept_text<N: AuthoredNode>(
    value: &N,
    valid: impl FnOnce(&str) -> Result<bool, Rejected>,
) -> Check {
    if valid(&string_value(value)?)? {
        Ok(())
    } else {
        Err(Rejected)
    }
}

fn valid_replay_on_change(text: &str) -> Result<bool, Rejected> {
    if one_of(text, &REPLAY_ON_CHANGE_ACTIONS) {
        return Ok(true);
    }
    match text.strip_prefix(BOUNDED_REPLAY_PREFIX) {
        Some(duration) => Ok(parse_duration(python_strip(duration)?)?.is_some()),
        None => Ok(false),
    }
}

fn check_cursor_rules<N: AuthoredNode>(
    config: &ConfigView<N>,
    values: &IncrementalValues<N>,
) -> Check {
    let cursor = values.cursor.as_deref();
    let cursor_type = values.cursor_type.as_deref();
    let grain = values.cursor_grain.as_deref();
    if cursor.is_some() && cursor_type.is_none() {
        return Err(Rejected);
    }
    if cursor_type.is_some_and(|value| !one_of(value, &CURSOR_TYPES)) {
        return Err(Rejected);
    }
    if grain.is_some()
        && (cursor_type != Some(TIMESTAMP_CURSOR)
            || !CURSOR_GRAIN_BATCH_SIZES
                .iter()
                .any(|(name, _)| Some(*name) == grain))
    {
        return Err(Rejected);
    }
    if cursor.is_some() && cursor_type == Some(TIMESTAMP_CURSOR) && grain.is_none() {
        return Err(Rejected);
    }
    let bounds = [values.cursor_start.as_ref(), values.cursor_end.as_ref()];
    if bounds.iter().any(Option::is_some) && (cursor.is_none() || cursor_type.is_none()) {
        return Err(Rejected);
    }
    if let Some(cursor_type) = cursor_type {
        let keys = bounds
            .iter()
            .flatten()
            .map(|bound| cursor_bound_key(*bound, cursor_type))
            .collect::<Result<Vec<_>, _>>()?;
        if let [start, end] = keys[..]
            && !keys_ordered(start, end, cursor_type)
        {
            return Err(Rejected);
        }
    }
    match config
        .get("append_cursor_inclusive")
        .map(AuthoredNode::kind)
    {
        None => Ok(()),
        Some(NodeKind::Bool(_))
            if values.strategy.as_deref() == Some(APPEND_STRATEGY) && cursor.is_some() =>
        {
            Ok(())
        }
        Some(_) => Err(Rejected),
    }
}

fn check_cursor_safety<N: AuthoredNode>(
    config: &ConfigView<N>,
    values: &IncrementalValues<N>,
) -> Check {
    let durations = ["cursor_start_max_ahead", "cursor_future_max_distance"];
    let actions = ["cursor_start_max_action", "cursor_future_action"];
    if values.cursor.is_none() && (config.any_present(&durations) || config.any_present(&actions)) {
        return Err(Rejected);
    }
    for key in durations {
        if let Some(value) = config.get(key) {
            accept_text(value, |text| {
                Ok(text == CURSOR_POLICY_DISABLED
                    || text == ZERO_DAY_DURATION
                    || parse_duration(text)?.is_some())
            })?;
        }
    }
    for key in actions {
        if let Some(value) = config.get(key) {
            accept_text(value, |text| Ok(one_of(text, &FUTURE_CURSOR_ACTIONS)))?;
        }
    }
    Ok(())
}

fn check_write_strategy<N: AuthoredNode>(
    config: &ConfigView<N>,
    values: &IncrementalValues<N>,
) -> Check {
    let strategy = values.strategy.as_deref();
    let has_unique_key = has_config_value(values.unique_key.as_ref());
    if strategy == Some(DELETE_INSERT_STRATEGY) && values.cursor.is_none() && !has_unique_key {
        return Err(Rejected);
    }
    if strategy == Some(MERGE_STRATEGY) && !has_unique_key {
        return Err(Rejected);
    }
    if let Some(excluded) = &values.merge_exclude_columns {
        let excluded = non_empty_strings(excluded)?;
        if strategy != Some(MERGE_STRATEGY) {
            return Err(Rejected);
        }
        reject_case_insensitive_duplicates(&excluded)?;
        let unique_columns = string_sequence(values.unique_key.as_ref())
            .iter()
            .map(|column| python_lower(column))
            .collect::<Result<HashSet<_>, _>>()?;
        for column in &excluded {
            if unique_columns.contains(&python_lower(column)?) {
                return Err(Rejected);
            }
        }
    }
    match config.get("full_refresh").map(AuthoredNode::kind) {
        None | Some(NodeKind::Bool(_)) => Ok(()),
        Some(_) => Err(Rejected),
    }
}

fn non_empty_strings<N: AuthoredNode>(value: &N) -> Result<Vec<String>, Rejected> {
    if !matches!(value.kind(), NodeKind::List | NodeKind::Tuple) {
        return Err(Rejected);
    }
    value
        .items()
        .iter()
        .map(|item| string_value(item).and_then(non_empty))
        .collect()
}

fn non_empty(text: String) -> Result<String, Rejected> {
    if text.is_empty() {
        Err(Rejected)
    } else {
        Ok(text)
    }
}

fn check_contract_columns<N: AuthoredNode>(
    config: &ConfigView<N>,
    values: &IncrementalValues<N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    let Some(declared) = contract_declared_columns(config, facts) else {
        return Ok(());
    };
    let named = values
        .cursor
        .iter()
        .cloned()
        .chain(string_sequence(values.unique_key.as_ref()))
        .chain(string_sequence(values.merge_exclude_columns.as_ref()));
    require_declared(named, &declared)
}

/// Return `_contract_declared_column_names` when the contract is enforced.
pub(crate) fn contract_declared_columns<N: AuthoredNode>(
    config: &ConfigView<N>,
    facts: &ModelValidationFacts<'_>,
) -> Option<HashSet<String>> {
    if !config.equals("contract", ENFORCED_CONTRACT) {
        return None;
    }
    let mut names: HashSet<String> = facts
        .declared_columns
        .unwrap_or_default()
        .iter()
        .cloned()
        .collect();
    if let Some(columns) = config
        .get("columns")
        .filter(|value| value.kind() == NodeKind::Map)
    {
        names.extend(
            columns
                .entries()
                .iter()
                .filter(|(key, _)| key.kind() == NodeKind::Str)
                .filter_map(|(key, _)| key.text()),
        );
    }
    Some(names)
}

/// Reject any column name the enforced contract does not declare.
pub(crate) fn require_declared(
    mut names: impl Iterator<Item = String>,
    declared: &HashSet<String>,
) -> Check {
    if names.all(|name| declared.contains(&name)) {
        Ok(())
    } else {
        Err(Rejected)
    }
}
