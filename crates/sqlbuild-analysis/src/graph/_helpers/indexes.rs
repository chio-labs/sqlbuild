//! Python's lineage edges, tag, path and name indexes over one project's resources.

use std::collections::HashMap;

use crate::assembly::project::types::ObjectKey;
use crate::graph::constants::SQL_TEST_RESOURCE;
use crate::graph::models::{GraphResource, ProjectGraph};

pub(crate) fn build(resources: &[GraphResource]) -> ProjectGraph {
    let mut graph = ProjectGraph::default();
    for resource in resources {
        if resource.key.0 == SQL_TEST_RESOURCE {
            continue;
        }
        let deps: Vec<ObjectKey> = resource
            .deps
            .iter()
            .filter(|dep| dep.0 != SQL_TEST_RESOURCE)
            .cloned()
            .collect();
        insert_list(
            &mut graph.upstream,
            &mut graph.upstream_index,
            &resource.key,
        )
        .clone_from(&deps);
    }
    graph.downstream = downstream(&graph.upstream);
    graph.downstream_index = positions(&graph.downstream);
    for resource in resources {
        for tag in &resource.tags {
            add_tag(&mut graph.tags, tag, &resource.key);
        }
        if let Some(folder) = &resource.folder {
            graph.paths.push((resource.key.clone(), folder.clone()));
        }
        set_name(&mut graph, &resource.key);
    }
    graph
}

/// The list stored for `key`, appended empty in insertion order when the key is new.
fn insert_list<'graph>(
    entries: &'graph mut Vec<(ObjectKey, Vec<ObjectKey>)>,
    index: &mut HashMap<ObjectKey, usize>,
    key: &ObjectKey,
) -> &'graph mut Vec<ObjectKey> {
    let position: usize = *index.entry(key.clone()).or_insert_with(|| {
        entries.push((key.clone(), Vec::new()));
        entries.len() - 1
    });
    &mut entries[position].1
}

fn downstream(upstream: &[(ObjectKey, Vec<ObjectKey>)]) -> Vec<(ObjectKey, Vec<ObjectKey>)> {
    let mut entries: Vec<(ObjectKey, Vec<ObjectKey>)> = Vec::new();
    let mut index: HashMap<ObjectKey, usize> = HashMap::new();
    for (key, _) in upstream {
        let _ = insert_list(&mut entries, &mut index, key);
    }
    for (key, deps) in upstream {
        for dep in deps {
            insert_list(&mut entries, &mut index, dep).push(key.clone());
        }
    }
    for (_, keys) in &mut entries {
        keys.sort();
    }
    entries
}

fn positions(entries: &[(ObjectKey, Vec<ObjectKey>)]) -> HashMap<ObjectKey, usize> {
    entries
        .iter()
        .enumerate()
        .map(|(position, (key, _))| (key.clone(), position))
        .collect()
}

fn add_tag(tags: &mut Vec<(String, Vec<ObjectKey>)>, tag: &str, key: &ObjectKey) {
    match tags.iter_mut().find(|(name, _)| name == tag) {
        Some((_, keys)) if keys.contains(key) => {}
        Some((_, keys)) => keys.push(key.clone()),
        None => tags.push((tag.to_owned(), vec![key.clone()])),
    }
}

fn set_name(graph: &mut ProjectGraph, key: &ObjectKey) {
    match graph.name_index.get(&key.1) {
        Some(&position) => graph.names[position].1 = key.clone(),
        None => {
            graph.name_index.insert(key.1.clone(), graph.names.len());
            graph.names.push((key.1.clone(), key.clone()));
        }
    }
}
