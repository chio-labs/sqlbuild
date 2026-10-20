use crate::event_export::models::{EventQueue, QueuedEvent};

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
        outcome: false,
        eligible_exporters: vec![0],
    }
}

/// A queued non-terminal event with `sequence`, `(priority, outcome)` and one eligible exporter.
pub(crate) fn event((priority, outcome): (u8, bool), sequence: u64) -> QueuedEvent<()> {
    QueuedEvent {
        outcome,
        ..queued(sequence, (priority, false))
    }
}

/// The sequences `queue` holds, ascending.
pub(crate) fn sequences(queue: &EventQueue<()>) -> Vec<u64> {
    let mut sequences: Vec<u64> = queue.items.iter().map(|item| item.sequence).collect();
    sequences.sort_unstable();
    sequences
}
