//! `_validate_incremental_batching`, raising the first error the Python validator raises.

use std::collections::HashSet;

use crate::model_validation::_helpers::config::{
    ConfigView, non_blank_string_check, one_of, python_str, sorted_values,
};
use crate::model_validation::_helpers::durations::parse_duration;
use crate::model_validation::_helpers::incremental::IncrementalValues;
use crate::model_validation::constants::{
    CAP_FROM_START_ACTION, CURSOR_INPUT_ROLES, DELETE_INSERT_STRATEGY, EFFECTIVE_BATCH_SIZE,
    FILTER_ROLE, INCREMENTAL_MODES, MERGE_STRATEGY, MICROBATCH_LIMIT_ACTIONS,
    MICROBATCH_LIMIT_KEYS, MICROBATCH_MODE, MICROBATCH_STRATEGIES, REMOVED_CURSOR_INPUT_KEYS,
    ROLLING_WINDOW_STRATEGY, TIMESTAMP_CURSOR, UNACCOUNTED_PARTITION_POLICIES,
    WATERMARK_BLOCK_KEYS, WATERMARK_MODES, WATERMARK_ROLE, WATERMARK_STRATEGY,
};
use crate::model_validation::models::{ModelValidationFacts, Rejected, ValidationStop};
use crate::model_validation::types::Check;
use crate::types::{AuthoredNode, NodeKind};

const COLUMN_KEY: &str = "column";
const ROLES_KEY: &str = "roles";

/// Check the batching, microbatch and cursor input rules.
pub(crate) fn check_incremental_batching<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    values: &IncrementalValues<N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    let mode = values.incremental_mode.as_deref();
    if let Some(mode) = mode
        && !one_of(mode, &INCREMENTAL_MODES)
    {
        return Err(config.error(format!(
            "unknown incremental_mode '{mode}'; valid values: {}",
            sorted_values(&INCREMENTAL_MODES)
        )));
    }
    let microbatch = mode == Some(MICROBATCH_MODE);
    if let Some(batch_size) = values.batch_size.as_deref() {
        if !microbatch {
            return Err(config.error("batch_size is only valid with incremental_mode=microbatch"));
        }
        if batch_size == EFFECTIVE_BATCH_SIZE
            && (values.cursor.is_none()
                || values.cursor_type.as_deref() != Some(TIMESTAMP_CURSOR)
                || values.cursor_grain.is_none())
        {
            return Err(
                config.error("batch_size=effective requires a timestamp cursor with cursor_grain")
            );
        }
    }
    check_state_config(config, values, microbatch)?;
    check_cursor_inputs(config, values, facts)?;
    if let Some(limit) = microbatch_limit(config, values)? {
        check_static_watermark_limit(config, values, &limit)?;
    }
    Ok(())
}

fn check_state_config<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    values: &IncrementalValues<N>,
    microbatch: bool,
) -> Check {
    if let Some(concurrency) = config.get("batch_concurrency") {
        let concurrent = match (concurrency.kind(), concurrency.integer()) {
            (NodeKind::Int { negative: false }, Some(value)) if value > 0 => value > 1,
            (NodeKind::Int { negative: false }, None) => true,
            _ => return Err(config.error("batch_concurrency must be a positive integer")),
        };
        if concurrent && !microbatch {
            return Err(config.error("batch_concurrency > 1 requires incremental_mode=microbatch"));
        }
        if concurrent && values.strategy.as_deref() != Some(DELETE_INSERT_STRATEGY) {
            return Err(
                config.error("batch_concurrency > 1 requires incremental_strategy=delete_insert")
            );
        }
    }
    if let Some(policy) = config.get("unaccounted_partition_policy") {
        if !UNACCOUNTED_PARTITION_POLICIES
            .iter()
            .any(|valid| policy.is_text(valid))
        {
            return Err(config.error(format!(
                "unaccounted_partition_policy must be one of: {}",
                sorted_values(&UNACCOUNTED_PARTITION_POLICIES)
            )));
        }
        if !microbatch {
            return Err(
                config.error("unaccounted_partition_policy requires incremental_mode=microbatch")
            );
        }
    }
    Ok(())
}

fn check_cursor_inputs<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    values: &IncrementalValues<N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    if let Some(key) = config.first_present(&REMOVED_CURSOR_INPUT_KEYS) {
        return Err(config.error(format!(
            "{key} has been removed; declare microbatch_strategy and use strategy-specific \
             cursor_inputs"
        )));
    }
    let microbatch = values.incremental_mode.as_deref() == Some(MICROBATCH_MODE);
    let strategy = values.microbatch_strategy.as_deref();
    let reference_count = facts.references.len();
    if strategy.is_some() && !microbatch {
        return Err(
            config.error("microbatch_strategy is only valid with incremental_mode=microbatch")
        );
    }
    if microbatch && strategy.is_none() {
        return Err(config.error(
            "incremental_mode=microbatch requires explicit microbatch_strategy \
             (rolling_window or watermark)",
        ));
    }
    if let Some(strategy) = strategy
        && !one_of(strategy, &MICROBATCH_STRATEGIES)
    {
        return Err(config.error(format!(
            "unknown microbatch_strategy '{strategy}'; valid values: {}",
            sorted_values(&MICROBATCH_STRATEGIES)
        )));
    }
    let watermark = strategy == Some(WATERMARK_STRATEGY);
    let rolling_window = strategy == Some(ROLLING_WINDOW_STRATEGY);
    if rolling_window && values.cursor_type.as_deref() != Some(TIMESTAMP_CURSOR) {
        return Err(config.error("rolling_window requires cursor_type=timestamp"));
    }
    let inputs = values.cursor_inputs.as_ref();
    if inputs.is_some() && values.cursor.is_none() {
        return Err(config.error("cursor_inputs requires cursor"));
    }
    if inputs.is_none() && (watermark || (rolling_window && reference_count > 0)) {
        return Err(config.error("microbatch strategy requires cursor_inputs"));
    }
    let input_names: HashSet<&str> = facts
        .references
        .iter()
        .map(|reference| reference.name.as_str())
        .collect();
    if let Some(inputs) = inputs {
        if watermark {
            check_watermark_inputs(config, inputs, &input_names)?;
        } else {
            check_input_map(config, inputs, &input_names)?;
        }
    }
    let watermark_mode = values.cursor_watermark_mode.as_deref();
    if watermark && !watermark_mode.is_some_and(|mode| one_of(mode, &WATERMARK_MODES)) {
        return Err(config.error("watermark strategy requires cursor_watermark_mode all or any"));
    }
    if !watermark && watermark_mode.is_some() {
        return Err(
            config.error("cursor_watermark_mode is only valid with microbatch_strategy=watermark")
        );
    }
    if let Some(limit) = &values.max_microbatches {
        if !is_positive_integer(limit) {
            return Err(config.error("max_microbatches must be a positive integer"));
        }
        if !watermark {
            return Err(
                config.error("max_microbatches is only valid with microbatch_strategy=watermark")
            );
        }
    }
    if values.cursor.is_some() && reference_count > 1 && inputs.is_none() {
        return Err(
            config.error("models with cursor and multiple inputs require explicit cursor_inputs")
        );
    }
    Ok(())
}

fn is_positive_integer<N: AuthoredNode>(value: &N) -> bool {
    match (value.kind(), value.integer()) {
        (NodeKind::Int { negative: false }, Some(number)) => number >= 1,
        (NodeKind::Int { negative: false }, None) => true,
        _ => false,
    }
}

fn expected_inputs(input_names: &HashSet<&str>) -> String {
    let mut names: Vec<&str> = input_names.iter().copied().collect();
    names.sort_unstable();
    names.join(", ")
}

fn check_input_map<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    inputs: &N,
    input_names: &HashSet<&str>,
) -> Check {
    if inputs.kind() != NodeKind::Map {
        return Err(config.error("cursor_inputs must be a relation map"));
    }
    let entries = inputs.entries();
    if entries.is_empty() {
        return Err(config.error("cursor_inputs must not be empty"));
    }
    for (relation, column) in &entries {
        if !non_blank_string_check(relation)? {
            return Err(config.error("cursor_inputs relation names must be non-empty strings"));
        }
        if !non_blank_string_check(column)? {
            let relation = relation.text().ok_or(Rejected)?;
            return Err(config.error(format!(
                "cursor_inputs column for relation '{relation}' must be a non-empty string"
            )));
        }
    }
    for (relation, _) in &entries {
        let relation = relation.text().ok_or(Rejected)?;
        if !input_names.contains(relation.as_str()) {
            return Err(config.error(format!(
                "cursor_inputs references unknown input '{relation}'; expected one of: {}",
                expected_inputs(input_names)
            )));
        }
    }
    Ok(())
}

fn check_watermark_inputs<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    inputs: &N,
    input_names: &HashSet<&str>,
) -> Check {
    let entries = inputs.entries();
    if inputs.kind() != NodeKind::Map || entries.is_empty() {
        return Err(config.error("watermark cursor_inputs must be a non-empty relation map"));
    }
    let mut has_watermark = false;
    for (relation, block) in &entries {
        if !non_blank_string_check(relation)? || block.kind() != NodeKind::Map {
            let relation = python_str(relation)?;
            return Err(config.error(format!(
                "watermark cursor_inputs relation '{relation}' must use \
                 (column ..., roles [...])"
            )));
        }
        let relation = relation.text().ok_or(Rejected)?;
        let block = block.entries();
        if !has_exact_keys(&block, &WATERMARK_BLOCK_KEYS) {
            return Err(config.error(format!(
                "cursor_inputs relation '{relation}' requires exactly column and roles"
            )));
        }
        let column = block_value(&block, COLUMN_KEY).ok_or(Rejected)?;
        if !non_blank_string_check(column)? {
            return Err(config.error(format!(
                "cursor_inputs column for relation '{relation}' must be a non-empty string"
            )));
        }
        let roles = block_value(&block, ROLES_KEY).ok_or(Rejected)?;
        let Some(roles) = valid_roles(roles)? else {
            return Err(config.error(format!(
                "cursor_inputs roles for relation '{relation}' must be a non-empty list \
                 containing only filter and/or watermark"
            )));
        };
        let distinct: HashSet<&&str> = roles.iter().collect();
        if distinct.len() != roles.len() {
            return Err(config.error(format!(
                "cursor_inputs relation '{relation}' contains duplicate roles"
            )));
        }
        has_watermark |= roles.contains(&WATERMARK_ROLE);
        if roles.contains(&FILTER_ROLE) && !input_names.contains(relation.as_str()) {
            return Err(config.error(format!(
                "filter role references input '{relation}' that is not directly filterable; \
                 expected one of: {}",
                expected_inputs(input_names)
            )));
        }
    }
    if has_watermark {
        Ok(())
    } else {
        Err(config.error("watermark strategy requires at least one watermark role"))
    }
}

/// Return whether a mapping's keys are exactly the strings `keys`, as `set(mapping) == keys`.
fn has_exact_keys<N: AuthoredNode>(block: &[(N, N)], keys: &[&str]) -> bool {
    if block.len() != keys.len() {
        return false;
    }
    for key in keys {
        if block_value(block, key).is_none() {
            return false;
        }
    }
    true
}

fn block_value<'b, N: AuthoredNode>(block: &'b [(N, N)], key: &str) -> Option<&'b N> {
    block
        .iter()
        .find(|(name, _)| name.is_text(key))
        .map(|(_, value)| value)
}

/// Return a non-empty list of valid roles, `None` when Python rejects it, or defer.
fn valid_roles<N: AuthoredNode>(roles: &N) -> Result<Option<Vec<&'static str>>, Rejected> {
    if roles.kind() != NodeKind::List {
        return Ok(None);
    }
    let items = roles.items();
    if items.is_empty() {
        return Ok(None);
    }
    let mut valid: Vec<&'static str> = Vec::with_capacity(items.len());
    for item in &items {
        match item.kind() {
            NodeKind::Str => match CURSOR_INPUT_ROLES.iter().find(|role| item.is_text(role)) {
                Some(role) => valid.push(role),
                None => return Ok(None),
            },
            NodeKind::Int { .. } | NodeKind::Bool(_) | NodeKind::Null => return Ok(None),
            _ => return Err(Rejected),
        }
    }
    Ok(Some(valid))
}

/// The resolved batch limit and its action, as `_validate_model_microbatch_limit` returns them.
struct MicrobatchLimit {
    /// The limit, or `None` for an integer too large to fall short of any requirement.
    max_batches: Option<i64>,
    cap_from_start: bool,
}

fn microbatch_limit<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    values: &IncrementalValues<N>,
) -> Result<Option<MicrobatchLimit>, ValidationStop> {
    let Some(limit) = &values.microbatch_limit else {
        return Ok(values
            .max_microbatches
            .as_ref()
            .filter(|limit| matches!(limit.kind(), NodeKind::Int { .. }))
            .map(|limit| MicrobatchLimit {
                max_batches: limit.integer(),
                cap_from_start: false,
            }));
    };
    if values.max_microbatches.is_some() {
        return Err(config.error("use either max_microbatches or microbatch_limit, not both"));
    }
    let block = limit.entries();
    if limit.kind() != NodeKind::Map || !has_exact_keys(&block, &MICROBATCH_LIMIT_KEYS) {
        return Err(config.error("microbatch_limit requires exactly max_batches and action"));
    }
    let [max_key, action_key] = MICROBATCH_LIMIT_KEYS;
    let max_batches = block_value(&block, max_key).ok_or(Rejected)?;
    if !is_positive_integer(max_batches) {
        return Err(config.error("microbatch_limit max_batches must be a positive integer"));
    }
    let action = block_value(&block, action_key).ok_or(Rejected)?;
    let Some(action) = MICROBATCH_LIMIT_ACTIONS
        .iter()
        .find(|valid| action.is_text(valid))
    else {
        return Err(config.error(format!(
            "microbatch_limit action must be one of: {}",
            sorted_values(&MICROBATCH_LIMIT_ACTIONS)
        )));
    };
    if values.microbatch_strategy.as_deref() != Some(WATERMARK_STRATEGY) {
        return Err(
            config.error("microbatch_limit is only valid with microbatch_strategy=watermark")
        );
    }
    Ok(Some(MicrobatchLimit {
        max_batches: max_batches.integer(),
        cap_from_start: *action == CAP_FROM_START_ACTION,
    }))
}

fn check_static_watermark_limit<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    values: &IncrementalValues<N>,
    limit: &MicrobatchLimit,
) -> Check {
    let batch_size = values.effective_batch_size();
    let rewrites_lookback = limit.cap_from_start
        && matches!(
            values.strategy.as_deref(),
            Some(DELETE_INSERT_STRATEGY | MERGE_STRATEGY)
        );
    let lookback = values
        .lookback
        .as_deref()
        .or(batch_size.filter(|_| rewrites_lookback));
    let (Some(lookback), Some(batch_size)) = (lookback, batch_size) else {
        return Ok(());
    };
    let (Some(lookback), Some(batch)) = (parse_duration(lookback)?, parse_duration(batch_size)?)
    else {
        return Ok(());
    };
    let lookback_batches = if lookback.total_months == 0 && batch.total_months == 0 {
        if batch.fixed_seconds == 0 {
            return Ok(());
        }
        lookback.fixed_seconds.div_ceil(batch.fixed_seconds)
    } else if lookback.fixed_seconds == 0 && batch.fixed_seconds == 0 {
        if batch.total_months == 0 {
            return Ok(());
        }
        lookback.total_months.div_ceil(batch.total_months)
    } else if limit.cap_from_start {
        return Err(config.error(
            "cap_from_start cannot prove forward progress when lookback and batch_size mix \
             calendar and fixed duration components; use compatible fixed or calendar durations",
        ));
    } else {
        return Ok(());
    };
    let required = lookback_batches + 1 + u128::from(limit.cap_from_start);
    let Some(max_batches) = limit.max_batches else {
        return Ok(());
    };
    let max = u128::try_from(max_batches).map_err(|_| Rejected)?;
    if max < required {
        Err(config.error(format!(
            "max_microbatches {max_batches} is below the ordinary lookback requirement of \
             {required} batches"
        )))
    } else {
        Ok(())
    }
}
