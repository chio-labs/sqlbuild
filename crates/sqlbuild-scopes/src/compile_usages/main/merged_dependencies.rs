//! A macro declaration's dependencies merged with the declarations its runtime uses consumed.

use std::collections::{HashMap, HashSet};
use std::hash::Hash;

use crate::compile_usages::models::DependencySource;

/// Per declaration, `None` without macro metadata, else own then consumed dependencies, deduped.
#[must_use]
pub fn merged_dependencies<K: Hash + Eq>(
    declarations: &[(K, Option<Vec<K>>)],
    usages: &[(Option<K>, K)],
) -> Vec<Option<Vec<DependencySource>>> {
    let mut by_consumer: HashMap<&K, Vec<usize>> = HashMap::new();
    for (position, (consumer, _)) in usages.iter().enumerate() {
        if let Some(consumer) = consumer {
            by_consumer.entry(consumer).or_default().push(position);
        }
    }
    let mut merged: Vec<Option<Vec<DependencySource>>> = Vec::with_capacity(declarations.len());
    for (identity, own) in declarations {
        let Some(own) = own else {
            merged.push(None);
            continue;
        };
        let mut seen: HashSet<&K> = HashSet::new();
        let mut sources: Vec<DependencySource> = Vec::new();
        for (position, dependency) in own.iter().enumerate() {
            if seen.insert(dependency) {
                sources.push(DependencySource::Own(position));
            }
        }
        for position in by_consumer.get(identity).into_iter().flatten() {
            if seen.insert(&usages[*position].1) {
                sources.push(DependencySource::Usage(*position));
            }
        }
        merged.push(Some(sources));
    }
    merged
}
