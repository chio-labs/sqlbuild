//! Insert into the bounded priority queue, displacing the oldest lower-priority event when full.

use crate::event_export::models::{EventQueue, QueueOutcome, QueuedEvent};

/// Queue `event` or reject it when full of events at least its priority; outcome events are never displaced and always admitted.
pub fn queue_lifecycle_event<T>(
    mut queue: EventQueue<T>,
    event: QueuedEvent<T>,
) -> QueueOutcome<T> {
    let mut displaced: Option<QueuedEvent<T>> = None;
    if queue.items.len() >= queue.capacity {
        let lowest: Option<u8> = queue
            .items
            .iter()
            .filter(|queued| !queued.outcome)
            .map(|queued| queued.priority)
            .min();
        let displaceable = lowest.filter(|lowest| event.outcome || *lowest < event.priority);
        let Some(lowest) = displaceable else {
            if event.outcome {
                queue.items.push(event);
                return QueueOutcome {
                    queue,
                    inserted: true,
                    displaced: None,
                    rejected: None,
                };
            }
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
            .filter(|(_, queued)| !queued.outcome && queued.priority == lowest)
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
