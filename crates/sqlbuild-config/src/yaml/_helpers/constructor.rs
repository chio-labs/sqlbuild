//! Build values from a composed document, as PyYAML's `SafeConstructor` does.

use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::ConfigValue;
use crate::yaml::_helpers::keys::{is_hashable, key_identity};
use crate::yaml::_helpers::numbers::{construct_float, construct_int};
use crate::yaml::_helpers::timestamps::construct_timestamp;
use crate::yaml::constants::{
    BASE_EXPANSION_BUDGET, BOOL_TAG, BOOL_WORDS, EXPANSION_BUDGET_PER_CHARACTER, FLOAT_TAG,
    INT_TAG, MAP_TAG, MAX_CONSTRUCTION_DEPTH, MERGE_TAG, NULL_TAG, PYTHON_ONLY_TAGS, SEQ_TAG,
    STR_TAG, TIMESTAMP_TAG, VALUE_TAG,
};
use crate::yaml::models::{ComposedDocument, Node, NodeContent};
use std::collections::HashMap;
use std::collections::hash_map::Entry;

/// One mapping entry after merge keys are flattened; `string_key` marks a `=` key read as text.
type FlatEntry = (usize, usize, bool);

fn construct_error(message: String) -> ConfigError {
    ConfigError::new(ConfigErrorKind::Construct, message)
}

fn construct_bool(text: &str) -> Result<ConfigValue, ConfigError> {
    let lowered = text.to_lowercase();
    BOOL_WORDS
        .iter()
        .find(|(word, _)| *word == lowered)
        .map(|(_, flag)| ConfigValue::Bool(*flag))
        .ok_or_else(|| construct_error(format!("{lowered:?} is not a YAML boolean")))
}

/// SafeConstructor's scalar constructors, by resolved tag.
fn construct_scalar(tag: &str, text: &str) -> Result<ConfigValue, ConfigError> {
    match tag {
        NULL_TAG => Ok(ConfigValue::Null),
        BOOL_TAG => construct_bool(text),
        INT_TAG => construct_int(text),
        FLOAT_TAG => construct_float(text),
        STR_TAG => Ok(ConfigValue::String(text.to_owned())),
        TIMESTAMP_TAG => construct_timestamp(text.strip_suffix('\n').unwrap_or(text)),
        _ if PYTHON_ONLY_TAGS.contains(&tag) => Err(ConfigError::new(
            ConfigErrorKind::Unsupported,
            format!("values tagged {tag} are left to Python"),
        )),
        SEQ_TAG | MAP_TAG => Err(construct_error(format!(
            "expected a collection node for {tag}"
        ))),
        _ => Err(construct_error(format!(
            "could not determine a constructor for the tag {tag:?}"
        ))),
    }
}

/// A constructed value and the number of values it holds, itself included.
type Sized = (ConfigValue, usize);

/// Construction state; values of nodes reached through several aliases are built once.
struct Constructor<'document> {
    document: &'document ComposedDocument,
    shared: Vec<bool>,
    built: HashMap<usize, (ConfigValue, usize, usize)>,
    budget: usize,
}

fn deferred(message: &str) -> ConfigError {
    ConfigError::new(ConfigErrorKind::Unsupported, message)
}

/// The nesting levels below a constructed value, which construction already bounds.
fn height(value: &ConfigValue) -> usize {
    match value {
        ConfigValue::List(items) => 1 + items.iter().map(height).max().unwrap_or_default(),
        ConfigValue::Map(entries) => {
            1 + entries
                .iter()
                .map(|(key, item)| height(key).max(height(item)))
                .max()
                .unwrap_or_default()
        }
        _ => 0,
    }
}

/// Whether each node is reachable from more than one place, through aliases.
fn shared_nodes(document: &ComposedDocument) -> Vec<bool> {
    let mut references = vec![0_usize; document.nodes.len()];
    for node in &document.nodes {
        match &node.content {
            NodeContent::Scalar(_) => {}
            NodeContent::Sequence(items) => {
                for item in items {
                    references[*item] += 1;
                }
            }
            NodeContent::Mapping(entries) => {
                for (key, value) in entries {
                    references[*key] += 1;
                    references[*value] += 1;
                }
            }
        }
    }
    references.into_iter().map(|count| count > 1).collect()
}

impl Constructor<'_> {
    fn node(&self, id: usize) -> &Node {
        &self.document.nodes[id]
    }

    /// Spend part of the budget, which bounds the values built, copied and merged per document.
    fn spend(&mut self, amount: usize) -> Result<(), ConfigError> {
        self.budget = self
            .budget
            .checked_sub(amount)
            .ok_or_else(|| deferred("aliases expand beyond the native size budget"))?;
        Ok(())
    }

    fn construct(&mut self, id: usize, depth: usize) -> Result<Sized, ConfigError> {
        if depth > MAX_CONSTRUCTION_DEPTH {
            return Err(deferred("values nest deeper than the native limit"));
        }
        if let Some((value, size, height)) = self.built.get(&id) {
            if depth + height > MAX_CONSTRUCTION_DEPTH {
                return Err(deferred("aliased values nest deeper than the native limit"));
            }
            let (value, size) = (value.clone(), *size);
            self.spend(size)?;
            return Ok((value, size));
        }
        self.spend(1)?;
        let built = self.construct_new(id, depth)?;
        if self.shared[id] {
            let (value, size) = &built;
            self.built.insert(id, (value.clone(), *size, height(value)));
        }
        Ok(built)
    }

    fn construct_new(&mut self, id: usize, depth: usize) -> Result<Sized, ConfigError> {
        let node = self.node(id);
        match (&node.content, node.tag.as_str()) {
            (NodeContent::Scalar(text), tag) => construct_scalar(tag, text).map(|value| (value, 1)),
            (NodeContent::Sequence(items), SEQ_TAG) => {
                let items = items.clone();
                let mut values: Vec<ConfigValue> = Vec::with_capacity(items.len());
                let mut size = 1;
                for item in items {
                    let (value, item_size) = self.construct(item, depth + 1)?;
                    values.push(value);
                    size += item_size;
                }
                Ok((ConfigValue::List(values), size))
            }
            (NodeContent::Mapping(_), MAP_TAG) => self.construct_mapping(id, depth),
            (_, tag) if PYTHON_ONLY_TAGS.contains(&tag) => Err(ConfigError::new(
                ConfigErrorKind::Unsupported,
                format!("values tagged {tag} are left to Python"),
            )),
            (_, tag) => Err(construct_error(format!(
                "could not construct a collection tagged {tag:?}"
            ))),
        }
    }

    /// The entries of a mapping node; merge keys accept only mappings and lists of mappings.
    fn entries(&self, id: usize) -> Result<Vec<(usize, usize)>, ConfigError> {
        match &self.node(id).content {
            NodeContent::Mapping(entries) => Ok(entries.clone()),
            _ => Err(construct_error(
                "expected a mapping or list of mappings for merging".to_owned(),
            )),
        }
    }

    /// The mappings a merge key's value contributes, in PyYAML's order.
    fn merged(&mut self, value: usize, depth: usize) -> Result<Vec<FlatEntry>, ConfigError> {
        let entries = match &self.node(value).content {
            NodeContent::Mapping(_) => self.flatten(value, depth + 1)?,
            NodeContent::Sequence(items) => {
                let mut parts: Vec<Vec<FlatEntry>> = Vec::new();
                for item in items.clone() {
                    self.entries(item)?;
                    parts.push(self.flatten(item, depth + 1)?);
                }
                parts.into_iter().rev().flatten().collect()
            }
            NodeContent::Scalar(_) => {
                return Err(construct_error(
                    "expected a mapping or list of mappings for merging".to_owned(),
                ));
            }
        };
        self.spend(entries.len())?;
        Ok(entries)
    }

    /// PyYAML's `flatten_mapping`: merged entries first, then the mapping's own entries.
    fn flatten(&mut self, id: usize, depth: usize) -> Result<Vec<FlatEntry>, ConfigError> {
        if depth > MAX_CONSTRUCTION_DEPTH {
            return Err(deferred("merge keys nest deeper than the native limit"));
        }
        let mut merged: Vec<FlatEntry> = Vec::new();
        let mut own: Vec<FlatEntry> = Vec::new();
        for (key, value) in self.entries(id)? {
            match self.node(key).tag.as_str() {
                MERGE_TAG => merged.extend(self.merged(value, depth)?),
                VALUE_TAG => own.push((key, value, true)),
                _ => own.push((key, value, false)),
            }
        }
        merged.extend(own);
        Ok(merged)
    }

    fn construct_key(
        &mut self,
        key: usize,
        string_key: bool,
        depth: usize,
    ) -> Result<Sized, ConfigError> {
        match (&self.node(key).content, string_key) {
            (NodeContent::Scalar(text), true) => {
                let text = text.clone();
                self.spend(1)?;
                Ok((ConfigValue::String(text), 1))
            }
            _ => self.construct(key, depth + 1),
        }
    }

    /// A Python dictionary: a repeated key keeps its first position and takes the last value.
    fn construct_mapping(&mut self, id: usize, depth: usize) -> Result<Sized, ConfigError> {
        let mut entries: Vec<(ConfigValue, ConfigValue)> = Vec::new();
        let mut size = 1;
        let mut positions: HashMap<String, usize> = HashMap::new();
        for (key, value, string_key) in self.flatten(id, depth)? {
            let (key, key_size) = self.construct_key(key, string_key, depth)?;
            if !is_hashable(&key) {
                return Err(construct_error("found unhashable key".to_owned()));
            }
            let (value, value_size) = self.construct(value, depth + 1)?;
            size += key_size + value_size;
            match positions.entry(key_identity(&key)) {
                Entry::Occupied(position) => entries[*position.get()].1 = value,
                Entry::Vacant(position) => {
                    position.insert(entries.len());
                    entries.push((key, value));
                }
            }
        }
        Ok((ConfigValue::Map(entries), size))
    }
}

/// The value of a composed document; an empty stream is `None` in Python, here `Null`.
pub(crate) fn construct_document(
    document: &ComposedDocument,
    text_length: usize,
) -> Result<ConfigValue, ConfigError> {
    let Some(root) = document.root else {
        return Ok(ConfigValue::Null);
    };
    let mut constructor = Constructor {
        document,
        shared: shared_nodes(document),
        built: HashMap::new(),
        budget: BASE_EXPANSION_BUDGET
            .saturating_add(text_length.saturating_mul(EXPANSION_BUDGET_PER_CHARACTER)),
    };
    constructor.construct(root, 0).map(|(value, _)| value)
}
