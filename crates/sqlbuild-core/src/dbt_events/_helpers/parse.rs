//! Reading node messages, starts and results from dbt events.

use crate::dbt_events::constants::{
    DEFAULT_MESSAGE_LEVEL, DEFAULT_RESOURCE_TYPE, NODE_FINISHED_EVENT, NODE_MESSAGE_EVENT_NAMES,
    NODE_MESSAGE_LEVELS, NODE_STARTED_EVENT_NAMES, OUTCOME_STATUSES, RESULT_EVENT_NAMES,
    START_STATUS, UNKNOWN_STATUS,
};
use crate::dbt_events::models::{DbtEvent, DbtNodeMessage, DbtNodeResult};
use crate::text::main::python_strip::python_strip;

/// Non-empty text, as dbt fields are read.
pub(crate) fn present(value: Option<&String>) -> Option<String> {
    value.filter(|text| !text.is_empty()).cloned()
}

fn named(event: &DbtEvent, names: &[&str]) -> bool {
    present(event.name.as_ref()).is_some_and(|name| names.contains(&name.as_str()))
}

/// Python's `total or num_models`.
fn event_total(event: &DbtEvent) -> Option<i64> {
    match event.total {
        Some(total) if total != 0 => Some(total),
        _ => event.num_models,
    }
}

/// The node's unique id, when the event names one.
pub(crate) fn unique_id(event: &DbtEvent) -> Option<String> {
    present(event.node.unique_id.as_ref())
}

/// A node-scoped warning or error message.
pub(crate) fn node_message(event: &DbtEvent) -> Option<DbtNodeMessage> {
    let level: Option<String> = present(event.level.as_ref());
    let level_matches: bool = level
        .as_ref()
        .is_some_and(|level| NODE_MESSAGE_LEVELS.contains(&level.as_str()));
    if !named(event, &NODE_MESSAGE_EVENT_NAMES) && !level_matches {
        return None;
    }
    unique_id(event)?;
    let message: String =
        present(event.data_msg.as_ref()).or_else(|| present(event.info_msg.as_ref()))?;
    Some(DbtNodeMessage {
        level: level.unwrap_or_else(|| DEFAULT_MESSAGE_LEVEL.to_owned()),
        message: python_strip(&message).to_owned(),
    })
}

fn base_result(event: &DbtEvent, unique_id: String, status: String) -> DbtNodeResult {
    DbtNodeResult {
        resource_type: present(event.node.resource_type.as_ref())
            .unwrap_or_else(|| DEFAULT_RESOURCE_TYPE.to_owned()),
        node_name: present(event.node.node_name.as_ref()).unwrap_or_else(|| unique_id.clone()),
        unique_id,
        status,
        index: event.index,
        total: event_total(event),
        materialized: present(event.node.materialized.as_ref()),
        ..DbtNodeResult::default()
    }
}

/// A START row for a node-started event.
pub(crate) fn node_start(event: &DbtEvent) -> Option<DbtNodeResult> {
    if !named(event, &NODE_STARTED_EVENT_NAMES) {
        return None;
    }
    Some(base_result(
        event,
        unique_id(event)?,
        START_STATUS.to_owned(),
    ))
}

/// The progress message for a node-started event.
pub(crate) fn start_message(result: &DbtNodeResult) -> String {
    format!(
        "Running dbt {} {}...",
        result.resource_type, result.node_name
    )
}

fn trusted_status(value: Option<&String>) -> Option<String> {
    present(value).filter(|status| OUTCOME_STATUSES.contains(&status.to_lowercase().as_str()))
}

/// A final node result, without its buffered messages.
pub(crate) fn node_result(event: &DbtEvent) -> Option<DbtNodeResult> {
    if !named(event, &RESULT_EVENT_NAMES) {
        return None;
    }
    let unique_id: String = unique_id(event)?;
    let node_status: Option<String> = present(event.node.node_status.as_ref());
    let status: Option<String> =
        if present(event.name.as_ref()).as_deref() == Some(NODE_FINISHED_EVENT) {
            present(event.run_result_status.as_ref()).or(node_status)
        } else {
            trusted_status(event.data_status.as_ref()).or(node_status)
        };
    Some(DbtNodeResult {
        execution_time: event.execution_time,
        relation_name: present(event.node.relation_name.as_ref()),
        database: present(event.node.database.as_ref()),
        schema: present(event.node.schema.as_ref()),
        node_checksum: present(event.node.node_checksum.as_ref()),
        ..base_result(
            event,
            unique_id,
            status.unwrap_or_else(|| UNKNOWN_STATUS.to_owned()),
        )
    })
}
