use sqlbuild_cursor::algebra::models::SortKey;

use crate::microbatches::models::{
    BoundInterval, CompletionFact, CursorBound, MicrobatchEventIdentity, TextInterval,
};

/// An integer cursor bound.
pub(crate) fn bound(value: i128) -> CursorBound {
    CursorBound {
        text: value.to_string(),
        key: SortKey::Integer(value),
    }
}

/// An integer interval `[start, end)`.
pub(crate) fn interval(start: i128, end: i128) -> BoundInterval {
    BoundInterval {
        start: bound(start),
        end: bound(end),
    }
}

/// A known-fingerprint ordinary completion created `created` seconds in.
pub(crate) fn completion(
    event_id: &str,
    (start, end): (i128, i128),
    created: f64,
) -> CompletionFact {
    CompletionFact {
        interval: interval(start, end),
        ordinary: true,
        unknown_fingerprint: false,
        created,
        event_id: event_id.to_owned(),
    }
}

/// The identity of an ordinary completion of `orders` over `[0, 1)`.
pub(crate) fn completion_identity() -> MicrobatchEventIdentity {
    MicrobatchEventIdentity {
        scope_kind: "direct_logical".to_owned(),
        scope_key: "duckdb:main.orders".to_owned(),
        model_name: "orders".to_owned(),
        target_database: None,
        target_schema: Some("main".to_owned()),
        target_name: "orders".to_owned(),
        physical_generation_id: "gen-1".to_owned(),
        record_type: "partition_completion".to_owned(),
        partition_start: Some("0".to_owned()),
        partition_end: Some("1".to_owned()),
        completion_reason: "initial".to_owned(),
    }
}

/// Interval texts as owned pairs.
pub(crate) fn texts(intervals: &[TextInterval]) -> Vec<(String, String)> {
    intervals
        .iter()
        .map(|interval| (interval.start.clone(), interval.end.clone()))
        .collect()
}

/// Borrowed pairs as owned pairs.
pub(crate) fn owned(pairs: &[(&str, &str)]) -> Vec<(String, String)> {
    pairs
        .iter()
        .map(|(start, end)| ((*start).to_owned(), (*end).to_owned()))
        .collect()
}
