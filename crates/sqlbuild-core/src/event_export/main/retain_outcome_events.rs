//! Keep only outcome events once the shutdown reserve begins.

use crate::event_export::models::{EventQueue, QueuedEvent};

/// The queue with only its outcome events, and every other event it held.
#[must_use]
pub fn retain_outcome_events<T>(mut queue: EventQueue<T>) -> (EventQueue<T>, Vec<QueuedEvent<T>>) {
    let (kept, dropped): (Vec<QueuedEvent<T>>, Vec<QueuedEvent<T>>) =
        queue.items.drain(..).partition(|queued| queued.outcome);
    queue.items = kept;
    (queue, dropped)
}
