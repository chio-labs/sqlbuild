//! Half-open interval construction, intersection, merging and batch splitting.

use std::cmp::Ordering;

use crate::algebra::_helpers::arithmetic::{
    advance_scalar, advance_scalar_by, floor_scalar, fresh, integer_sum,
};
use crate::algebra::_helpers::civil::midnight;
use crate::algebra::_helpers::comparison::{compare_scalars, key_ordering, sort_key, unorderable};
use crate::algebra::_helpers::failures::algebra;
use crate::algebra::constants::{NON_POSITIVE_STEP, TEMPORAL_PARTITIONS_NEED_GRAIN};
use crate::algebra::errors::CursorError;
use crate::algebra::models::{
    Grain, Interval, Scalar, ScalarValue, SortKey, Timestamp, ZoneOffset,
};
use crate::algebra::types::ZoneRules;

/// The canonical partition containing an observed value.
pub(crate) fn observed_partition_value(
    value: &Scalar,
    grain: Option<Grain>,
) -> Result<Interval, CursorError> {
    if let ScalarValue::Integer(number) = &value.value {
        let end: Scalar = fresh(ScalarValue::Integer(integer_sum(*number, 1)?));
        return Ok(Interval {
            start: value.clone(),
            end,
            grain: None,
        });
    }
    let Some(grain) = grain else {
        return Err(algebra(TEMPORAL_PARTITIONS_NEED_GRAIN));
    };
    let observed: Scalar = match &value.value {
        ScalarValue::Date(date) if grain <= Grain::Hour => {
            fresh(ScalarValue::Timestamp(Timestamp {
                local: midnight(*date),
                fold: false,
                offset: ZoneOffset::Naive,
                template: None,
                source_text: None,
            }))
        }
        _ => value.clone(),
    };
    let start: Scalar = floor_scalar(&observed, Some(grain));
    let end: Scalar = advance_scalar(&start, Some(grain))?;
    Ok(Interval {
        start,
        end,
        grain: Some(grain),
    })
}

/// The intersection of two intervals, if it is not empty.
pub(crate) fn clamp_interval(
    interval: &Interval,
    bounds: &Interval,
    rules: &dyn ZoneRules,
) -> Result<Option<Interval>, CursorError> {
    let start: &Scalar = if compare_scalars(&interval.start, &bounds.start, rules)?.is_ge() {
        &interval.start
    } else {
        &bounds.start
    };
    let end: &Scalar = if compare_scalars(&interval.end, &bounds.end, rules)?.is_le() {
        &interval.end
    } else {
        &bounds.end
    };
    if compare_scalars(start, end, rules)?.is_ge() {
        return Ok(None);
    }
    Ok(Some(Interval {
        start: start.clone(),
        end: end.clone(),
        grain: interval.grain,
    }))
}

/// The intervals stably ordered by start, as `sorted` orders them.
fn ordered_by_start(
    intervals: &[Interval],
    rules: &dyn ZoneRules,
) -> Result<Vec<Interval>, CursorError> {
    let keys: Vec<SortKey> = intervals
        .iter()
        .map(|interval| sort_key(&interval.start, rules))
        .collect::<Result<_, _>>()?;
    if let Some(pair) = keys
        .windows(2)
        .find(|pair| key_ordering(&pair[1], &pair[0]).is_none())
    {
        return Err(unorderable("<", &pair[1], &pair[0]));
    }
    let mut order: Vec<usize> = (0..intervals.len()).collect();
    order.sort_by(|left, right| {
        key_ordering(&keys[*left], &keys[*right]).unwrap_or(Ordering::Equal)
    });
    Ok(order
        .into_iter()
        .map(|index| intervals[index].clone())
        .collect())
}

/// Overlapping or adjacent intervals merged, in start order.
pub(crate) fn merge_interval_values(
    intervals: &[Interval],
    rules: &dyn ZoneRules,
) -> Result<Vec<Interval>, CursorError> {
    let mut merged: Vec<Interval> = Vec::new();
    for interval in ordered_by_start(intervals, rules)? {
        let Some(last) = merged.last_mut() else {
            merged.push(interval);
            continue;
        };
        if compare_scalars(&last.end, &interval.start, rules)?.is_lt() {
            merged.push(interval);
        } else if compare_scalars(&last.end, &interval.end, rules)?.is_lt() {
            last.end = interval.end;
            last.grain = interval.grain;
        }
    }
    Ok(merged)
}

/// Consecutive batches of `step` grains covering `interval`, the last one possibly shorter.
pub(crate) fn split_interval(
    interval: &Interval,
    step: i64,
    rules: &dyn ZoneRules,
) -> Result<Vec<Interval>, CursorError> {
    if step <= 0 {
        return Err(algebra(NON_POSITIVE_STEP));
    }
    let mut batches: Vec<Interval> = Vec::new();
    let mut start: Scalar = interval.start.clone();
    while compare_scalars(&start, &interval.end, rules)?.is_lt() {
        let mut end: Scalar = advance_scalar_by(&start, interval.grain, step)?;
        if compare_scalars(&end, &interval.end, rules)?.is_gt() {
            end = interval.end.clone();
        }
        batches.push(Interval {
            start,
            end: end.clone(),
            grain: interval.grain,
        });
        start = end;
    }
    Ok(batches)
}
