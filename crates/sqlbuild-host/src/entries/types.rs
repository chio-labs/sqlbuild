//! The resolution of host entries, which the Python boundary implements.

use crate::entries::models::HostId;

/// Resolves host entries to the boundary's values, the one way native code reaches Python.
pub trait HostEntries {
    /// A resolved entry: a function, class, exception or value.
    type Entry;
    /// Why an entry could not be resolved.
    type Error;

    /// The entry `id` names, resolved on every call.
    fn entry(&self, id: HostId) -> Result<Self::Entry, Self::Error>;
}
