use crate::event_export::models::QueuedEvent;

/// A queued unit event with `sequence`, `(priority, invocation terminal)` and one eligible exporter.
pub(crate) fn queued(
    sequence: u64,
    (priority, invocation_terminal): (u8, bool),
) -> QueuedEvent<()> {
    QueuedEvent {
        sequence,
        item: (),
        priority,
        invocation_terminal,
        eligible_exporters: vec![0],
    }
}
