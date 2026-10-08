//! `_validate_incremental_batching` for configs Python certainly accepts.

use std::collections::HashSet;

use crate::model_validation::_helpers::config::{
    ConfigView, non_blank_string, one_of, optional_one_of, string_value,
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
use crate::model_validation::models::{ModelValidationFacts, Rejected};
use crate::model_validation::types::Check;
use crate::types::{AuthoredNode, NodeKind};

/// Accept the batching, microbatch and cursor input rules.
pub(crate) fn check_incremental_batching<N: AuthoredNode>(
    values: &IncrementalValues<N>,
    config: &ConfigView<N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    let mode = values.incremental_mode.as_deref();
    if mode.is_some_and(|value| !one_of(value, &INCREMENTAL_MODES)) {
        return Err(Rejected);
    }
    let microbatch = mode == Some(MICROBATCH_MODE);
    if let Some(batch_size) = values.batch_size.as_deref() {
        if !microbatch {
            return Err(Rejected);
        }
        if batch_size == EFFECTIVE_BATCH_SIZE
            && (values.cursor.is_none()
                || values.cursor_type.as_deref() != Some(TIMESTAMP_CURSOR)
                || values.cursor_grain.is_none())
        {
            return Err(Rejected);
        }
    }
    check_state_config(values, config, microbatch)?;
    if config.any_present(&REMOVED_CURSOR_INPUT_KEYS) {
        return Err(Rejected);
    }
    check_cursor_inputs(values, facts)?;
    if let Some(limit) = microbatch_limit(values)? {
        check_static_watermark_limit(values, limit)?;
    }
    Ok(())
}

fn check_state_config<N: AuthoredNode>(
    values: &IncrementalValues<N>,
    config: &ConfigView<N>,
    microbatch: bool,
) -> Check {
    if let Some(concurrency) = config.get("batch_concurrency") {
        let concurrency = concurrency.integer().ok_or(Rejected)?;
        if concurrency <= 0
            || (concurrency > 1
                && (!microbatch || values.strategy.as_deref() != Some(DELETE_INSERT_STRATEGY)))
        {
            return Err(Rejected);
        }
    }
    if let Some(policy) = config.get("unaccounted_partition_policy")
        && (!one_of(&string_value(policy)?, &UNACCOUNTED_PARTITION_POLICIES) || !microbatch)
    {
        return Err(Rejected);
    }
    Ok(())
}

fn check_cursor_inputs<N: AuthoredNode>(
    values: &IncrementalValues<N>,
    facts: &ModelValidationFacts<'_>,
) -> Check {
    let microbatch = values.incremental_mode.as_deref() == Some(MICROBATCH_MODE);
    let strategy = values.microbatch_strategy.as_deref();
    let reference_count = facts.references.len();
    if strategy.is_some() != microbatch
        || strategy.is_some_and(|value| !one_of(value, &MICROBATCH_STRATEGIES))
    {
        return Err(Rejected);
    }
    if strategy == Some(ROLLING_WINDOW_STRATEGY)
        && values.cursor_type.as_deref() != Some(TIMESTAMP_CURSOR)
    {
        return Err(Rejected);
    }
    let inputs = values.cursor_inputs.as_ref();
    if inputs.is_some() && values.cursor.is_none() {
        return Err(Rejected);
    }
    if inputs.is_none()
        && (strategy == Some(WATERMARK_STRATEGY)
            || (strategy == Some(ROLLING_WINDOW_STRATEGY) && reference_count > 0))
    {
        return Err(Rejected);
    }
    let input_names: HashSet<&str> = facts
        .references
        .iter()
        .map(|reference| reference.name.as_str())
        .collect();
    if let Some(inputs) = inputs {
        if strategy == Some(WATERMARK_STRATEGY) {
            check_watermark_inputs(inputs, &input_names)?;
        } else {
            check_input_map(inputs, &input_names)?;
        }
    }
    let watermark_mode = values.cursor_watermark_mode.as_deref();
    if (strategy == Some(WATERMARK_STRATEGY) && !optional_one_of(watermark_mode, &WATERMARK_MODES))
        || (strategy != Some(WATERMARK_STRATEGY) && watermark_mode.is_some())
    {
        return Err(Rejected);
    }
    if let Some(limit) = &values.max_microbatches
        && (limit.integer().is_none_or(|value| value < 1) || strategy != Some(WATERMARK_STRATEGY))
    {
        return Err(Rejected);
    }
    if values.cursor.is_some() && reference_count > 1 && inputs.is_none() {
        return Err(Rejected);
    }
    Ok(())
}

fn check_input_map<N: AuthoredNode>(inputs: &N, input_names: &HashSet<&str>) -> Check {
    let entries = map_entries(inputs)?;
    if entries.is_empty() {
        return Err(Rejected);
    }
    for (relation, column) in &entries {
        let relation = non_blank_string(relation)?;
        non_blank_string(column)?;
        if !input_names.contains(relation.as_str()) {
            return Err(Rejected);
        }
    }
    Ok(())
}

fn check_watermark_inputs<N: AuthoredNode>(inputs: &N, input_names: &HashSet<&str>) -> Check {
    let entries = map_entries(inputs)?;
    if entries.is_empty() {
        return Err(Rejected);
    }
    let mut has_watermark = false;
    for (relation, block) in &entries {
        let relation = non_blank_string(relation)?;
        let block = keyed_entries(block, &WATERMARK_BLOCK_KEYS)?;
        non_blank_string(&block[0])?;
        let roles = &block[1];
        if roles.kind() != NodeKind::List {
            return Err(Rejected);
        }
        let roles = roles
            .items()
            .iter()
            .map(string_value)
            .collect::<Result<Vec<_>, _>>()?;
        let distinct: HashSet<&String> = roles.iter().collect();
        if roles.is_empty()
            || roles.iter().any(|role| !one_of(role, &CURSOR_INPUT_ROLES))
            || distinct.len() != roles.len()
        {
            return Err(Rejected);
        }
        has_watermark |= roles.iter().any(|role| role == WATERMARK_ROLE);
        if roles.iter().any(|role| role == FILTER_ROLE) && !input_names.contains(relation.as_str())
        {
            return Err(Rejected);
        }
    }
    if has_watermark { Ok(()) } else { Err(Rejected) }
}

fn map_entries<N: AuthoredNode>(value: &N) -> Result<Vec<(N, N)>, Rejected> {
    if value.kind() == NodeKind::Map {
        Ok(value.entries())
    } else {
        Err(Rejected)
    }
}

/// Return a mapping's values in `keys` order when its keys are exactly `keys`.
fn keyed_entries<N: AuthoredNode>(value: &N, keys: &[&str]) -> Result<Vec<N>, Rejected> {
    let entries = map_entries(value)?;
    if entries.len() != keys.len() {
        return Err(Rejected);
    }
    keys.iter().map(|key| entry_value(&entries, key)).collect()
}

fn entry_value<N: AuthoredNode>(entries: &[(N, N)], key: &str) -> Result<N, Rejected> {
    for (name, item) in entries {
        if name.kind() == NodeKind::Str && name.is_text(key) {
            return Ok(item.clone());
        }
    }
    Err(Rejected)
}

/// The resolved batch limit and its action, as `_validate_model_microbatch_limit` returns them.
struct MicrobatchLimit {
    max_batches: i64,
    cap_from_start: bool,
}

fn microbatch_limit<N: AuthoredNode>(
    values: &IncrementalValues<N>,
) -> Result<Option<MicrobatchLimit>, Rejected> {
    let Some(limit) = &values.microbatch_limit else {
        return Ok(values
            .max_microbatches
            .as_ref()
            .and_then(AuthoredNode::integer)
            .map(|max_batches| MicrobatchLimit {
                max_batches,
                cap_from_start: false,
            }));
    };
    if values.max_microbatches.is_some() {
        return Err(Rejected);
    }
    let block = keyed_entries(limit, &MICROBATCH_LIMIT_KEYS)?;
    let max_batches = block[0]
        .integer()
        .filter(|value| *value >= 1)
        .ok_or(Rejected)?;
    let action = string_value(&block[1])?;
    if !one_of(&action, &MICROBATCH_LIMIT_ACTIONS)
        || values.microbatch_strategy.as_deref() != Some(WATERMARK_STRATEGY)
    {
        return Err(Rejected);
    }
    Ok(Some(MicrobatchLimit {
        max_batches,
        cap_from_start: action == CAP_FROM_START_ACTION,
    }))
}

fn check_static_watermark_limit<N: AuthoredNode>(
    values: &IncrementalValues<N>,
    limit: MicrobatchLimit,
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
        return Err(Rejected);
    } else {
        return Ok(());
    };
    let required = lookback_batches + 1 + u128::from(limit.cap_from_start);
    let max_batches = u128::try_from(limit.max_batches).map_err(|_| Rejected)?;
    if max_batches < required {
        Err(Rejected)
    } else {
        Ok(())
    }
}
