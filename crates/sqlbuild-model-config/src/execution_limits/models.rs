//! A parsed per-item execution limit.

/// An execution limit: whole seconds, or explicitly disabled.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ExecutionLimit {
    Seconds(u64),
    Disabled,
}
