//! Insert into the bounded priority queue, displacing the oldest lower-priority event when full.

use crate::event_export::models::{EventQueue, QueueOutcome, QueuedEvent};

/// Queue `event`, or reject it when every queued event has at least its priority.
pub fn queue_lifecycle_event<T>(
    mut queue: EventQueue<T>,
    event: QueuedEvent<T>,
) -> QueueOutcome<T> {
    let mut displaced: Option<QueuedEvent<T>> = None;
    if queue.items.len() >= queue.capacity {
        let lowest: Option<u8> = queue.items.iter().map(|queued| queued.priority).min();
        let Some(lowest) = lowest.filter(|lowest| *lowest < event.priority) else {
            return QueueOutcome {
                queue,
                inserted: false,
                displaced: None,
                rejected: Some(event),
            };
        };
        let position: Option<usize> = queue
            .items
            .iter()
            .enumerate()
            .filter(|(_, queued)| queued.priority == lowest)
            .min_by_key(|(_, queued)| queued.sequence)
            .map(|(position, _)| position);
        displaced = position.map(|position| queue.items.remove(position));
    }
    queue.items.push(event);
    QueueOutcome {
        queue,
        inserted: true,
        displaced,
        rejected: None,
    }
}
