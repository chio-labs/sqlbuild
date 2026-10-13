//! `argparse.Namespace` attribute access.

use crate::argv::models::{Namespace, Value};

impl Namespace {
    /// `getattr(namespace, name)`, when the attribute exists.
    pub(crate) fn get(&self, name: &str) -> Option<&Value> {
        self.entries
            .iter()
            .find(|(entry, _)| entry == name)
            .map(|(_, value)| value)
    }

    /// `hasattr(namespace, name)`.
    pub(crate) fn has(&self, name: &str) -> bool {
        self.get(name).is_some()
    }

    /// `setattr(namespace, name, value)`, keeping the first assignment's position.
    pub(crate) fn set(&mut self, name: &str, value: Value) {
        match self.entries.iter_mut().find(|(entry, _)| entry == name) {
            Some((_, existing)) => *existing = value,
            None => self.entries.push((name.to_owned(), value)),
        }
    }

    /// The attribute's value, or `None` when it is missing.
    pub(crate) fn value(&self, name: &str) -> Value {
        self.get(name).cloned().unwrap_or(Value::None)
    }
}
