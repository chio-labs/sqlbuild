//! Python dict semantics over ordered pairs, and the topological analysis waves.

use std::collections::{BTreeSet, HashMap};

use crate::assembly::analysis_session::constants::DIALECT_ALIASES;
use crate::assembly::analysis_session::models::ModelRequest;
use crate::assembly::analysis_session::types::{Pairs, Shapes};
use crate::semantic_validation::models::Columns;
use crate::semantic_validation::types::Relations;

/// Python's `dict(pairs)`: the first position of each key with its last value.
pub(crate) fn dict_from_pairs(pairs: impl IntoIterator<Item = (String, String)>) -> Pairs {
    let mut positions: HashMap<String, usize> = HashMap::new();
    let mut result: Pairs = Vec::new();
    for (key, value) in pairs {
        if let Some(position) = positions.get(&key) {
            result[*position].1 = value;
            continue;
        }
        positions.insert(key.clone(), result.len());
        result.push((key, value));
    }
    result
}

/// Python's `dict ==`: the same items in any order.
pub(crate) fn same_mapping(left: &Pairs, right: &Pairs) -> bool {
    let right: HashMap<&str, &str> = right
        .iter()
        .map(|(key, value)| (key.as_str(), value.as_str()))
        .collect();
    left.len() == right.len()
        && left
            .iter()
            .all(|(key, value)| right.get(key.as_str()) == Some(&value.as_str()))
}

/// Python's `dict.keys() ==`: the same keys in any order.
pub(crate) fn same_keys(left: &Pairs, right: &Pairs) -> bool {
    let right: HashMap<&str, &str> = right
        .iter()
        .map(|(key, value)| (key.as_str(), value.as_str()))
        .collect();
    left.len() == right.len() && left.iter().all(|(key, _)| right.contains_key(key.as_str()))
}

/// Python's `dict ==` over `{relation: {column: type}}`.
pub(crate) fn same_relations(left: &Shapes, right: &Shapes) -> bool {
    let right: HashMap<&str, &Pairs> = right
        .iter()
        .map(|(name, shape)| (name.as_str(), shape))
        .collect();
    if left.len() != right.len() {
        return false;
    }
    for (name, shape) in left {
        match right.get(name.as_str()) {
            Some(other) if same_mapping(shape, other) => {}
            _ => return false,
        }
    }
    true
}

/// Python's `dict[name] = value` over ordered pairs.
pub(crate) fn with_pair(mut pairs: Pairs, key: &str, value: &str) -> Pairs {
    match pairs.iter().position(|(existing, _)| existing == key) {
        Some(position) => value.clone_into(&mut pairs[position].1),
        None => pairs.push((key.to_owned(), value.to_owned())),
    }
    pairs
}

/// Relation shapes by name, keeping Python's `setdefault` semantics.
#[derive(Debug, Clone, Default)]
pub(crate) struct ShapeTable {
    shapes: HashMap<String, Pairs>,
    /// Each name at its first insertion, Python's dict iteration order.
    order: Vec<String>,
}

impl ShapeTable {
    pub(crate) fn from_shapes(shapes: &Shapes) -> Self {
        let mut table: Self = Self::default();
        for (name, shape) in shapes {
            if table.shapes.insert(name.clone(), shape.clone()).is_none() {
                table.order.push(name.clone());
            }
        }
        table
    }

    /// The shapes in Python's dict iteration order.
    pub(crate) fn ordered(&self) -> Vec<(&str, &Pairs)> {
        self.order
            .iter()
            .filter_map(|name| self.shapes.get_key_value(name))
            .map(|(name, shape)| (name.as_str(), shape))
            .collect()
    }

    pub(crate) fn get(&self, name: &str) -> Option<&Pairs> {
        self.shapes.get(name)
    }

    pub(crate) fn contains(&self, name: &str) -> bool {
        self.shapes.contains_key(name)
    }

    /// Python's `setdefault`.
    pub(crate) fn set_default(&mut self, name: &str, shape: Pairs) {
        if !self.shapes.contains_key(name) {
            self.shapes.insert(name.to_owned(), shape);
            self.order.push(name.to_owned());
        }
    }
}

/// Native catalog columns for a `{name: type}` shape.
pub(crate) fn catalog_columns(shape: &Pairs) -> Columns {
    Columns(
        shape
            .iter()
            .map(|(name, value)| (name.clone(), Some(value.clone())))
            .collect(),
    )
}

/// Native catalog relations for ordered shapes.
pub(crate) fn catalog_relations<'a>(
    shapes: impl IntoIterator<Item = &'a (String, Pairs)>,
) -> Relations {
    shapes
        .into_iter()
        .map(|(name, shape)| (name.clone(), catalog_columns(shape)))
        .collect()
}

/// Python's `NATIVE_DIALECT_ALIASES.get(dialect, dialect)`.
pub(crate) fn native_dialect(dialect: &str) -> &str {
    DIALECT_ALIASES
        .iter()
        .find(|(alias, _)| *alias == dialect)
        .map_or(dialect, |(_, native)| native)
}

/// Each model's analysed `ref` producers, or None when two models share a name.
pub(crate) fn producers(models: &[ModelRequest]) -> Option<Vec<Vec<usize>>> {
    let mut indexes: HashMap<&str, usize> = HashMap::with_capacity(models.len());
    for (index, model) in models.iter().enumerate() {
        if indexes.insert(model.name.as_str(), index).is_some() {
            return None;
        }
    }
    let mut producers: Vec<Vec<usize>> = Vec::with_capacity(models.len());
    for model in models {
        let mut model_producers: BTreeSet<usize> = BTreeSet::new();
        for reference in model
            .references
            .iter()
            .filter(|reference| reference.model_ref)
        {
            if let Some(index) = indexes.get(reference.analysis_name.as_str()) {
                model_producers.insert(*index);
            }
        }
        producers.push(model_producers.into_iter().collect());
    }
    Some(producers)
}

/// `TopologicalSorter` waves in request order, or None when the graph has a cycle.
pub(crate) fn waves(producers: &[Vec<usize>]) -> Option<Vec<Vec<usize>>> {
    let mut pending: Vec<usize> = producers.iter().map(Vec::len).collect();
    let mut consumers: Vec<Vec<usize>> = vec![Vec::new(); producers.len()];
    for (model, model_producers) in producers.iter().enumerate() {
        for producer in model_producers {
            consumers[*producer].push(model);
        }
    }
    let mut ready: Vec<usize> = (0..producers.len())
        .filter(|model| pending[*model] == 0)
        .collect();
    let mut waves: Vec<Vec<usize>> = Vec::new();
    let mut scheduled: usize = 0;
    while !ready.is_empty() {
        scheduled += ready.len();
        let mut next: Vec<usize> = Vec::new();
        for model in &ready {
            for consumer in &consumers[*model] {
                pending[*consumer] -= 1;
                if pending[*consumer] == 0 {
                    next.push(*consumer);
                }
            }
        }
        next.sort_unstable();
        waves.push(std::mem::replace(&mut ready, next));
    }
    (scheduled == producers.len()).then_some(waves)
}
