//! Poisoned model outputs in Python's dict order, spread along compiled lineage.

use std::collections::HashMap;

use crate::semantic_checks::models::LineageOutput;

/// Python's `dict[tuple[str, str], CompilerDiagnostic]` keyed by `(model, column)`.
#[derive(Debug, Default)]
pub(crate) struct Poison {
    order: Vec<(String, String)>,
    roots: HashMap<(String, String), usize>,
}

impl Poison {
    pub(crate) fn len(&self) -> usize {
        self.order.len()
    }

    pub(crate) fn is_empty(&self) -> bool {
        self.order.is_empty()
    }

    pub(crate) fn get(&self, model: &str, column: &str) -> Option<usize> {
        self.roots
            .get(&(model.to_owned(), column.to_owned()))
            .copied()
    }

    /// `poisoned[key] = root`: a new key goes last, an existing key keeps its place.
    pub(crate) fn insert(&mut self, model: &str, column: &str, root: usize) {
        let key = (model.to_owned(), column.to_owned());
        if self.roots.insert(key.clone(), root).is_none() {
            self.order.push(key);
        }
    }

    /// `poisoned.setdefault(key, root)`.
    pub(crate) fn set_default(&mut self, model: &str, column: &str, root: usize) {
        let key = (model.to_owned(), column.to_owned());
        if !self.roots.contains_key(&key) {
            self.roots.insert(key.clone(), root);
            self.order.push(key);
        }
    }

    /// Entries in insertion order.
    pub(crate) fn entries(&self) -> impl Iterator<Item = (&(String, String), usize)> {
        self.order
            .iter()
            .map(|key| (key, self.roots.get(key).copied().unwrap_or_default()))
    }

    /// Python's bounded fixed point: one pass per model, stopping when a pass adds nothing.
    pub(crate) fn spread<'a>(
        &mut self,
        models: impl Iterator<Item = (&'a str, &'a [LineageOutput])> + Clone,
    ) {
        let passes = models.clone().count();
        for _ in 0..passes {
            let previous = self.len();
            for (name, lineage) in models.clone() {
                for output in lineage {
                    for (resource, column) in &output.upstream {
                        if let Some(root) = self.get(resource, column) {
                            self.set_default(name, &output.output_column, root);
                        }
                    }
                }
            }
            if self.len() == previous {
                break;
            }
        }
    }
}
