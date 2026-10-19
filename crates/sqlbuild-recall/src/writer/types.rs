//! The hook a Recall replacement sink plugs into delivery.

use crate::records::models::OutputChunk;
use crate::writer::models::{ReplacedEvents, ReplacedOutput};

/// Decides, on the delivery thread, what Recall stores for each output chunk.
pub trait OutputReplacement: Send + Sync + std::fmt::Debug {
    /// What to store for `chunk`: its replacement bytes, nothing, or nothing because the replacement failed.
    fn replace(&self, chunk: &OutputChunk) -> ReplacedOutput;
}

/// A lifecycle event waiting for the replacement sink, which decides on the delivery thread what Recall stores for it.
pub trait PendingLifecycleEvent: Send + std::fmt::Debug {
    /// The events to store in place of this one, nothing, or nothing because the replacement failed.
    fn replace(self: Box<Self>) -> ReplacedEvents;
}
