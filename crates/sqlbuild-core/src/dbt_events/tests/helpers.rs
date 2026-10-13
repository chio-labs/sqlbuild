use crate::dbt_events::main::consume_dbt_event::consume_dbt_event;
use crate::dbt_events::models::{
    DbtEvent, DbtEventNode, DbtNodeMessage, DbtNodeResult, DbtStreamRow, DbtStreamState,
    DbtStreamUpdate,
};

fn text(value: &str) -> Option<String> {
    Some(value.to_owned())
}

/// A dbt event named `name` for the node `unique_id`.
pub(super) fn event(name: &str, unique_id: &str) -> DbtEvent {
    DbtEvent {
        name: text(name),
        level: text("info"),
        node: DbtEventNode {
            unique_id: text(unique_id),
            resource_type: text("model"),
            node_name: text(unique_id.rsplit('.').next().unwrap_or_default()),
            ..DbtEventNode::default()
        },
        ..DbtEvent::default()
    }
}

/// A final model result event with a status, timing and counter.
pub(super) fn result_event(name: &str, unique_id: &str, status: &str) -> DbtEvent {
    DbtEvent {
        data_status: text(status),
        index: Some(1),
        total: Some(0),
        num_models: Some(2),
        execution_time: Some(0.125),
        ..event(name, unique_id)
    }
}

/// An error message event for the node `unique_id`.
pub(super) fn message_event(unique_id: &str, message: &str) -> DbtEvent {
    DbtEvent {
        level: text("error"),
        data_msg: text(""),
        info_msg: text(message),
        ..event("RunResultError", unique_id)
    }
}

/// The updates a fresh stream reports for `events`.
pub(super) fn updates(events: &[DbtEvent]) -> Vec<Option<DbtStreamUpdate>> {
    let mut state: DbtStreamState = DbtStreamState::default();
    let mut updates: Vec<Option<DbtStreamUpdate>> = Vec::new();
    for event in events {
        let (next, update) = consume_dbt_event(state, event);
        state = next;
        updates.push(update);
    }
    updates
}

/// The update for a node-started event at `display_index`.
pub(super) fn started(unique_id: &str, display_index: i64) -> Option<DbtStreamUpdate> {
    Some(DbtStreamUpdate {
        status_message: Some(format!(
            "Running dbt model {}...",
            unique_id.rsplit('.').next().unwrap_or_default()
        )),
        row: Some(DbtStreamRow {
            result: DbtNodeResult {
                unique_id: unique_id.to_owned(),
                resource_type: "model".to_owned(),
                node_name: unique_id.rsplit('.').next().unwrap_or_default().to_owned(),
                status: "start".to_owned(),
                ..DbtNodeResult::default()
            },
            display_index,
            finished: false,
        }),
    })
}

/// The update for a final model result.
pub(super) fn finished(
    unique_id: &str,
    (status, display_index): (&str, i64),
    messages: Vec<DbtNodeMessage>,
) -> Option<DbtStreamUpdate> {
    Some(DbtStreamUpdate {
        status_message: None,
        row: Some(DbtStreamRow {
            result: DbtNodeResult {
                unique_id: unique_id.to_owned(),
                resource_type: "model".to_owned(),
                node_name: unique_id.rsplit('.').next().unwrap_or_default().to_owned(),
                status: status.to_owned(),
                index: Some(1),
                total: Some(2),
                execution_time: Some(0.125),
                messages,
                ..DbtNodeResult::default()
            },
            display_index,
            finished: true,
        }),
    })
}
