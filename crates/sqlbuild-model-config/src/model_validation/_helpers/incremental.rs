//! `validate_incremental_config`, raising the first error the Python validator raises.

use std::collections::HashSet;

use crate::model_validation::_helpers::config::{
    ConfigView, has_config_value, one_of, sorted_values, string_sequence,
};
use crate::model_validation::_helpers::cursor_bounds::{
    BoundKey, bound_key, check_bound, keys_ordered,
};
use crate::model_validation::_helpers::durations::parse_duration;
use crate::model_validation::_helpers::microbatch::check_incremental_batching;
use crate::model_validation::_helpers::text::{model_header_help, python_lower, python_strip};
use crate::model_validation::constants::{
    APPEND_STRATEGY, BOUNDED_REPLAY_PREFIX, CURSOR_GRAIN_BATCH_SIZES, CURSOR_INPUT_KEYS,
    CURSOR_POLICY_DISABLED, CURSOR_TYPES, DELETE_INSERT_STRATEGY, EFFECTIVE_BATCH_SIZE,
    ENFORCED_CONTRACT, FUTURE_CURSOR_ACTIONS, INCREMENTAL_MATERIALIZATION, INCREMENTAL_STRATEGIES,
    MERGE_STRATEGY, ON_SCHEMA_CHANGE_EXAMPLE, ON_SCHEMA_CHANGE_POLICIES, REPLAY_ON_CHANGE_ACTIONS,
    REPLAY_ON_CHANGE_EXAMPLE, REPLAY_ON_CHANGE_VALID_VALUES, TABLE_MATERIALIZATION,
    TIMESTAMP_CURSOR, VIEW_MATERIALIZATION, ZERO_DAY_DURATION,
};
use crate::model_validation::models::{ModelValidationFacts, Rejected, ValidationStop};
use crate::model_validation::types::Check;
use crate::types::{AuthoredNode, NodeKind};

const ON_SCHEMA_CHANGE_KEY: &str = "on_schema_change";
const REPLAY_ON_CHANGE_KEY: &str = "replay_on_change";
const CURSOR_SAFETY_DURATION_KEYS: [&str; 2] =
    ["cursor_start_max_ahead", "cursor_future_max_distance"];
const CURSOR_SAFETY_ACTION_KEYS: [&str; 2] = ["cursor_start_max_action", "cursor_future_action"];

/// The incremental config values `_resolve_incremental_config_values` reads, in its order.
pub(crate) struct IncrementalValues<N> {
    pub(crate) strategy: Option<String>,
    pub(crate) cursor: Option<String>,
    pub(crate) cursor_type: Option<String>,
    pub(crate) lookback: Option<String>,
    pub(crate) incremental_mode: Option<String>,
    pub(crate) batch_size: Option<String>,
    pub(crate) microbatch_strategy: Option<String>,
    pub(crate) cursor_watermark_mode: Option<String>,
    pub(crate) cursor_grain: Option<String>,
    pub(crate) cursor_start: Option<N>,
    pub(crate) cursor_end: Option<N>,
    pub(crate) unique_key: Option<N>,
    pub(crate) cursor_inputs: Option<N>,
    pub(crate) max_microbatches: Option<N>,
    pub(crate) microbatch_limit: Option<N>,
    pub(crate) merge_exclude_columns: Option<N>,
}

impl<N: AuthoredNode> IncrementalValues<N> {
    fn read(config: &ConfigView<'_, N>) -> Result<Self, ValidationStop> {
        let node = |key: &str| config.get(key).cloned();
        let strategy = config.string("incremental_strategy")?;
        let cursor = config.string("cursor")?;
        let cursor_type = config.string("cursor_type")?;
        let lookback = config.string("lookback")?;
        let incremental_mode = config.string("incremental_mode")?;
        let batch_size = config.string("batch_size")?;
        let microbatch_strategy = config.string("microbatch_strategy")?;
        let cursor_watermark_mode = config.string("cursor_watermark_mode")?;
        let cursor_grain = config.string("cursor_grain")?;
        Ok(Self {
            strategy,
            cursor,
            cursor_type,
            lookback,
            incremental_mode,
            batch_size,
            microbatch_strategy,
            cursor_watermark_mode,
            cursor_grain,
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

/// Check the incremental rules for one model's layered config.
pub(crate) fn check_incremental<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    let materialized = config.string("materialized")?;
    let materialized = materialized.as_deref();
    if matches!(
        materialized,
        Some(TABLE_MATERIALIZATION | VIEW_MATERIALIZATION)
    ) && let Some(key) = config.first_present(&CURSOR_INPUT_KEYS)
    {
        return Err(config.error(format!(
            "{key} requires cursor-based incremental materialization"
        )));
    }
    if materialized != Some(INCREMENTAL_MATERIALIZATION) {
        return Ok(());
    }
    let values = IncrementalValues::read(config)?;
    check_core(config, &values)?;
    check_incremental_batching(config, &values, facts)?;
    check_write_strategy(config, &values)?;
    check_contract_columns(config, &values, facts)?;
    if values.lookback.is_some() && values.cursor.is_none() {
        return Err(config.error("lookback is only valid with cursor-based incremental"));
    }
    Ok(())
}

fn check_core<N: AuthoredNode>(config: &ConfigView<'_, N>, values: &IncrementalValues<N>) -> Check {
    for (key, example) in [
        (ON_SCHEMA_CHANGE_KEY, ON_SCHEMA_CHANGE_EXAMPLE),
        (REPLAY_ON_CHANGE_KEY, REPLAY_ON_CHANGE_EXAMPLE),
    ] {
        if let Some(value) = config.get(key)
            && let Some(problem) = change_policy_problem(key, value)?
        {
            let help =
                model_header_help(&format!("use a valid {key}"), &format!("{key} {example}"));
            return Err(ValidationStop::Error(
                config.config_error(problem).with_help(help),
            ));
        }
    }
    let Some(strategy) = values.strategy.as_deref() else {
        return Err(config.error("incremental materialization requires incremental_strategy"));
    };
    if !one_of(strategy, &INCREMENTAL_STRATEGIES) {
        return Err(config.error(format!(
            "unknown incremental_strategy '{strategy}'; valid values: {}",
            sorted_values(&INCREMENTAL_STRATEGIES)
        )));
    }
    check_cursor_rules(config, values)?;
    check_cursor_safety(config, values)
}

/// Return `change_policy_problem`: why a change-policy value is invalid, or `None`.
fn change_policy_problem<N: AuthoredNode>(
    key: &str,
    value: &N,
) -> Result<Option<String>, Rejected> {
    let valid = if key == ON_SCHEMA_CHANGE_KEY {
        sorted_values(&ON_SCHEMA_CHANGE_POLICIES)
    } else {
        REPLAY_ON_CHANGE_VALID_VALUES.join(", ")
    };
    if value.kind() != NodeKind::Str {
        return Ok(Some(format!(
            "{key} must be a string; valid values: {valid}"
        )));
    }
    let text = value.text().ok_or(Rejected)?;
    if key == ON_SCHEMA_CHANGE_KEY && one_of(&text, &ON_SCHEMA_CHANGE_POLICIES) {
        return Ok(None);
    }
    if key == REPLAY_ON_CHANGE_KEY {
        if one_of(&text, &REPLAY_ON_CHANGE_ACTIONS) {
            return Ok(None);
        }
        if let Some(rest) = text.strip_prefix(BOUNDED_REPLAY_PREFIX) {
            let duration = python_strip(rest)?;
            if parse_duration(duration)?.is_some() {
                return Ok(None);
            }
            return Ok(Some(format!(
                "{key} '{text}' has an invalid duration '{duration}'; use a positive duration \
                 such as 14d, 12h or 1mo"
            )));
        }
    }
    Ok(Some(format!(
        "unknown {key} '{text}'; valid values: {valid}"
    )))
}

fn check_cursor_rules<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    values: &IncrementalValues<N>,
) -> Check {
    let cursor = values.cursor.as_deref();
    let cursor_type = values.cursor_type.as_deref();
    let grain = values.cursor_grain.as_deref();
    let grains: Vec<&str> = CURSOR_GRAIN_BATCH_SIZES
        .iter()
        .map(|(name, _)| *name)
        .collect();
    if cursor.is_some() && cursor_type.is_none() {
        return Err(config.error(format!(
            "cursor requires cursor_type (valid values: {})",
            sorted_values(&CURSOR_TYPES)
        )));
    }
    if let Some(cursor_type) = cursor_type
        && !one_of(cursor_type, &CURSOR_TYPES)
    {
        return Err(config.error(format!(
            "unknown cursor_type '{cursor_type}'; valid values: {}",
            sorted_values(&CURSOR_TYPES)
        )));
    }
    if grain.is_some() && cursor_type != Some(TIMESTAMP_CURSOR) {
        return Err(config.error("cursor_grain is only valid with cursor_type=timestamp"));
    }
    if let Some(grain) = grain
        && !one_of(grain, &grains)
    {
        return Err(config.error(format!(
            "unknown cursor_grain '{grain}'; valid values: {}",
            sorted_values(&grains)
        )));
    }
    if cursor.is_some() && cursor_type == Some(TIMESTAMP_CURSOR) && grain.is_none() {
        return Err(config.error(format!(
            "cursor_type=timestamp requires cursor_grain (valid values: {})",
            sorted_values(&grains)
        )));
    }
    if let Some(start) = &values.cursor_start {
        if cursor.is_none() {
            return Err(config.error("cursor_start requires cursor"));
        }
        if cursor_type.is_none() {
            return Err(config.error("cursor_start requires cursor_type"));
        }
        check_bound(config, start, cursor_type)?;
    }
    if let Some(end) = &values.cursor_end {
        if cursor.is_none() {
            return Err(config.error("cursor_end requires cursor"));
        }
        check_bound(config, end, cursor_type)?;
    }
    if let (Some(start), Some(end), Some(cursor_type)) =
        (&values.cursor_start, &values.cursor_end, cursor_type)
    {
        let start_key = ordering_key(config, start, cursor_type, "cursor_start")?;
        let end_key = ordering_key(config, end, cursor_type, "cursor_end")?;
        if !keys_ordered(start_key, end_key, cursor_type)? {
            return Err(config.error("cursor_start must be before exclusive cursor_end"));
        }
    }
    check_append_cursor_inclusive(config, values)
}

fn ordering_key<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    bound: &N,
    cursor_type: &str,
    key: &str,
) -> Result<i128, ValidationStop> {
    match bound_key(bound, cursor_type)? {
        BoundKey::Key(value) => Ok(value),
        BoundKey::Overflow(utc_value) => {
            let text = bound.text().ok_or(Rejected)?;
            let help = model_header_help(
                &format!("keep {key} within years 1-9999 in UTC"),
                &format!("{key} '{utc_value}'"),
            );
            Err(ValidationStop::Error(
                config
                    .config_error(format!(
                        "{key} value '{text}' falls outside years 1-9999 once converted to UTC"
                    ))
                    .with_help(help),
            ))
        }
    }
}

fn check_append_cursor_inclusive<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    values: &IncrementalValues<N>,
) -> Check {
    let Some(inclusive) = config.get("append_cursor_inclusive") else {
        return Ok(());
    };
    if !matches!(inclusive.kind(), NodeKind::Bool(_)) {
        return Err(config.error("append_cursor_inclusive must be a boolean"));
    }
    if values.strategy.as_deref() != Some(APPEND_STRATEGY) {
        return Err(config.error("append_cursor_inclusive is only valid with append strategy"));
    }
    if values.cursor.is_none() {
        return Err(config.error("append_cursor_inclusive requires cursor"));
    }
    Ok(())
}

fn check_cursor_safety<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    values: &IncrementalValues<N>,
) -> Check {
    if values.cursor.is_none()
        && (config.first_present(&CURSOR_SAFETY_DURATION_KEYS).is_some()
            || config.first_present(&CURSOR_SAFETY_ACTION_KEYS).is_some())
    {
        return Err(config.error("cursor safety overrides require cursor"));
    }
    for key in CURSOR_SAFETY_DURATION_KEYS {
        if let Some(value) = config.get(key)
            && !safety_duration_check(value)?
        {
            return Err(config.error(format!("{key} must be a duration or 'disabled'")));
        }
    }
    for key in CURSOR_SAFETY_ACTION_KEYS {
        let Some(value) = config.get(key) else {
            continue;
        };
        let valid = match value.kind() {
            NodeKind::Str => FUTURE_CURSOR_ACTIONS
                .iter()
                .any(|action| value.is_text(action)),
            NodeKind::Int { .. } | NodeKind::Bool(_) => false,
            _ => return Err(ValidationStop::Defer),
        };
        if !valid {
            return Err(config.error(format!("{key} must be one of: cap, error")));
        }
    }
    Ok(())
}

fn safety_duration_check<N: AuthoredNode>(value: &N) -> Result<bool, Rejected> {
    if value.kind() != NodeKind::Str {
        return Ok(false);
    }
    let text = value.text().ok_or(Rejected)?;
    Ok(text == CURSOR_POLICY_DISABLED
        || text == ZERO_DAY_DURATION
        || parse_duration(&text)?.is_some())
}

fn check_write_strategy<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    values: &IncrementalValues<N>,
) -> Check {
    let strategy = values.strategy.as_deref();
    let has_unique_key = has_config_value(values.unique_key.as_ref());
    if strategy == Some(DELETE_INSERT_STRATEGY) && values.cursor.is_none() && !has_unique_key {
        return Err(config.error("delete_insert without cursor requires unique_key"));
    }
    if strategy == Some(MERGE_STRATEGY) && !has_unique_key {
        return Err(config.error("merge strategy requires unique_key"));
    }
    if let Some(excluded) = &values.merge_exclude_columns {
        if !is_non_empty_string_list(excluded) {
            return Err(config.error("merge_exclude_columns must be a list of non-empty strings"));
        }
        let excluded = string_sequence(Some(excluded))?;
        if strategy != Some(MERGE_STRATEGY) {
            return Err(config.error("merge_exclude_columns requires incremental_strategy=merge"));
        }
        let lowered = excluded
            .iter()
            .map(|column| python_lower(column))
            .collect::<Result<Vec<String>, Rejected>>()?;
        let distinct: HashSet<&String> = lowered.iter().collect();
        if distinct.len() != lowered.len() {
            return Err(config.error("merge_exclude_columns contains duplicate columns"));
        }
        let unique_columns = string_sequence(values.unique_key.as_ref())?
            .iter()
            .map(|column| python_lower(column))
            .collect::<Result<HashSet<String>, Rejected>>()?;
        let overlap: Vec<&str> = excluded
            .iter()
            .zip(&lowered)
            .filter(|(_, lower)| unique_columns.contains(*lower))
            .map(|(column, _)| column.as_str())
            .collect();
        if !overlap.is_empty() {
            return Err(config.error(format!(
                "merge_exclude_columns cannot include unique_key column(s): {}",
                overlap.join(", ")
            )));
        }
    }
    match config.get("full_refresh").map(AuthoredNode::kind) {
        None | Some(NodeKind::Bool(_)) => Ok(()),
        Some(_) => Err(config.error("full_refresh must be a boolean")),
    }
}

/// Return whether a value is a list or tuple of non-empty strings, as `_validated_string_sequence`.
fn is_non_empty_string_list<N: AuthoredNode>(value: &N) -> bool {
    matches!(value.kind(), NodeKind::List | NodeKind::Tuple)
        && value.items().iter().all(|item| {
            item.kind() == NodeKind::Str && !item.with_text(str::is_empty).unwrap_or(false)
        })
}

fn check_contract_columns<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    values: &IncrementalValues<N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    let Some(declared) = contract_declared_columns(config, facts) else {
        return Ok(());
    };
    if let Some(cursor) = &values.cursor {
        require_declared(config, "cursor", std::slice::from_ref(cursor), &declared)?;
    }
    require_declared(
        config,
        "unique_key",
        &string_sequence(values.unique_key.as_ref())?,
        &declared,
    )?;
    require_declared(
        config,
        "merge_exclude_columns",
        &string_sequence(values.merge_exclude_columns.as_ref())?,
        &declared,
    )
}

/// Return `_contract_declared_column_names` when the contract is enforced.
pub(crate) fn contract_declared_columns<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
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

/// Raise for the first of `names` the enforced contract does not declare.
pub(crate) fn require_declared<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    key: &str,
    names: &[String],
    declared: &HashSet<String>,
) -> Check {
    match names.iter().find(|name| !declared.contains(*name)) {
        Some(name) => Err(config.error(format!(
            "{key} references column '{name}' not declared in enforced contract"
        ))),
        None => Ok(()),
    }
}
