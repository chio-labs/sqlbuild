use crate::progress::main::claim_progress_terminal::claim_progress_terminal;
use crate::progress::main::close_progress_projection::close_progress_projection;
use crate::progress::main::consume_progress_event::consume_progress_event;
use crate::progress::models::{
    ProgressEvent, ProgressPayload, ProgressProjection, ProgressSettings,
};
use crate::progress::tests::test_types::ProjectionTestCase;
use crate::terminal_events::models::TerminalRequest;

/// One `orders` resource attempt event.
pub(super) fn attempt_event(
    event_id: &str,
    event_type: &str,
    (attempt_id, duration_ms): (&str, Option<f64>),
) -> ProgressEvent {
    ProgressEvent {
        event_id: event_id.to_owned(),
        event_type: event_type.to_owned(),
        resource_id: Some("model:orders".to_owned()),
        resource_attempt_id: Some(attempt_id.to_owned()),
        payload: ProgressPayload {
            resource_name: Some("orders".to_owned()),
            resource_kind: Some("table".to_owned()),
            duration_ms,
            ..ProgressPayload::default()
        },
        ..ProgressEvent::default()
    }
}

/// One operation event, optionally inside the `orders` attempt.
pub(super) fn operation_event(
    event_id: &str,
    event_type: &str,
    (operation_name, attempt_id): (&str, Option<&str>),
) -> ProgressEvent {
    ProgressEvent {
        event_id: event_id.to_owned(),
        event_type: event_type.to_owned(),
        resource_id: attempt_id.map(|_| "model:orders".to_owned()),
        resource_attempt_id: attempt_id.map(str::to_owned),
        operation_id: Some("op1".to_owned()),
        payload: ProgressPayload {
            operation_name: Some(operation_name.to_owned()),
            duration_ms: Some(1500.0),
            ..ProgressPayload::default()
        },
        ..ProgressEvent::default()
    }
}

/// Every line a case writes, then the durations its claims return.
pub(super) fn project_case(test_case: &ProjectionTestCase) -> (Vec<String>, Vec<Option<f64>>) {
    let mut projection: ProgressProjection = ProgressProjection::new(test_case.settings);
    for name in &test_case.enriched {
        projection.expect_resource_enrichment(name);
    }
    let mut lines: Vec<String> = Vec::new();
    for event in &test_case.events {
        let (consumed, event_lines) = consume_progress_event(projection, event);
        projection = consumed;
        lines.extend(event_lines);
    }
    let mut durations: Vec<Option<f64>> = Vec::new();
    for request in &test_case.claims {
        let (claimed, claim_lines, duration) = claim_progress_terminal(projection, request);
        projection = claimed;
        lines.extend(claim_lines);
        durations.push(duration);
    }
    lines.extend(close_progress_projection(projection).1);
    (lines, durations)
}

/// A claim for `orders` by name only.
pub(super) fn orders_claim() -> TerminalRequest {
    TerminalRequest {
        resource_name: "orders".to_owned(),
        ..TerminalRequest::default()
    }
}

/// Settings of a plain, non-terminal, non-debug stream.
pub(super) fn plain() -> ProgressSettings {
    ProgressSettings::default()
}
