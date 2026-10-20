//! A config mapping's entries.

use crate::config_values::models::ConfigNode;

/// A mapping's `(key, value)` entries in insertion order, as a Python `dict` keeps them.
pub type ConfigEntries<H> = Vec<(ConfigNode<H>, ConfigNode<H>)>;

/// What config logic asks of an opaque value's handle, read only when it is needed.
pub trait HostObject: Clone {
    /// Whether the value is a `datetime.date` or `datetime.datetime`.
    fn is_date_like(&self) -> bool;
    /// Python's `str(node)`, or `repr(node)`, of a value the crate does not print exactly itself.
    fn display(node: &ConfigNode<Self>, repr: bool) -> String;
}

/// Python's `str()` of a value that is not a plain scalar, or the error it raises.
pub type ItemText<'t, H, E> = &'t dyn Fn(&ConfigNode<H>) -> Result<String, E>;
