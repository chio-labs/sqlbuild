//! Selector resolution failures.

/// A resolver failure, or an invalid path selector with its message.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DbtSelectionError<E> {
    Resolver(E),
    PathSelector(String),
}
