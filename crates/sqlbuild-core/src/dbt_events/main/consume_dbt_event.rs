//! Advance the dbt stream by one event.

use crate::dbt_events::_helpers::parse::{
    node_message, node_result, node_start, start_message, unique_id,
};
use crate::dbt_events::models::{
    DbtEvent, DbtNodeResult, DbtStreamRow, DbtStreamState, DbtStreamUpdate,
};

/// Buffer node messages, number started nodes, and report each node's first final result once.
pub fn consume_dbt_event(
    mut state: DbtStreamState,
    event: &DbtEvent,
) -> (DbtStreamState, Option<DbtStreamUpdate>) {
    let result: Option<DbtNodeResult> = node_result(event);
    if result.is_none()
        && let Some(message) = node_message(event)
    {
        if let Some(unique_id) = unique_id(event) {
            state
                .pending_messages
                .entry(unique_id)
                .or_default()
                .push(message);
        }
        return (state, None);
    }
    if let Some(start) = node_start(event) {
        let status_message: Option<String> = Some(start_message(&start));
        if state.started_indexes.contains_key(&start.unique_id) {
            let update: DbtStreamUpdate = DbtStreamUpdate {
                status_message,
                row: None,
            };
            return (state, Some(update));
        }
        state.display_index += 1;
        state
            .started_indexes
            .insert(start.unique_id.clone(), state.display_index);
        let update: DbtStreamUpdate = DbtStreamUpdate {
            status_message,
            row: Some(DbtStreamRow {
                result: start,
                display_index: state.display_index,
                finished: false,
            }),
        };
        return (state, Some(update));
    }
    let Some(mut result) = result else {
        return (state, None);
    };
    result.messages = state
        .pending_messages
        .remove(&result.unique_id)
        .unwrap_or_default();
    result.messages.extend(node_message(event));
    if !state.recorded_unique_ids.insert(result.unique_id.clone()) {
        return (state, None);
    }
    let display_index: i64 = match state.started_indexes.get(&result.unique_id) {
        Some(index) => *index,
        None => {
            state.display_index += 1;
            state.display_index
        }
    };
    let update: DbtStreamUpdate = DbtStreamUpdate {
        status_message: None,
        row: Some(DbtStreamRow {
            result,
            display_index,
            finished: true,
        }),
    };
    (state, Some(update))
}
