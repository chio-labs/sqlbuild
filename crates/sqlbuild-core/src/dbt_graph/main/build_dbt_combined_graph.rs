//! Build the combined graph from manifest models and compiled SQLBuild models.

use std::collections::HashSet;

use crate::dbt_graph::_helpers::edges::{ensure, inverted, push, sort_targets};
use crate::dbt_graph::models::{
    DbtCombinedGraph, DbtGraphEdges, DbtGraphKey, DbtGraphManifest, DbtGraphProjectModel,
};

fn add_dbt_edges(mut upstream: DbtGraphEdges, manifest: &DbtGraphManifest) -> DbtGraphEdges {
    let model_ids: HashSet<&str> = manifest
        .models
        .iter()
        .map(|model| model.unique_id.as_str())
        .collect();
    for model in &manifest.models {
        let key: DbtGraphKey = DbtGraphKey::dbt_model(&model.unique_id);
        upstream = ensure(upstream, &key);
        for dependency in &model.depends_on_nodes {
            if model_ids.contains(dependency.as_str()) {
                upstream = push(upstream, &key, DbtGraphKey::dbt_model(dependency));
            }
            if manifest.source_ids.contains(dependency) {
                let source: DbtGraphKey = DbtGraphKey::dbt_source(dependency);
                upstream = push(ensure(upstream, &source), &key, source);
            }
            if manifest.seed_ids.contains(dependency) {
                let seed: DbtGraphKey = DbtGraphKey::dbt_source(dependency);
                upstream = push(ensure(upstream, &seed), &key, seed);
            }
        }
    }
    upstream
}

fn add_sqlbuild_edges(
    mut upstream: DbtGraphEdges,
    models: &[DbtGraphProjectModel],
) -> DbtGraphEdges {
    let names: HashSet<&str> = models.iter().map(|model| model.name.as_str()).collect();
    for model in models {
        let key: DbtGraphKey = DbtGraphKey::sqlbuild_model(&model.name);
        upstream = ensure(upstream, &key);
        for dependency in &model.model_deps {
            if names.contains(dependency.as_str()) {
                upstream = push(upstream, &key, DbtGraphKey::sqlbuild_model(dependency));
            }
        }
        for unique_id in &model.dbt_ref_unique_ids {
            upstream = push(upstream, &key, DbtGraphKey::dbt_model(unique_id));
        }
    }
    upstream
}

/// Upstream edges from dbt and SQLBuild dependencies, and their inversion, sorted by stable ID.
#[must_use]
pub fn build_dbt_combined_graph(
    manifest: &DbtGraphManifest,
    models: &[DbtGraphProjectModel],
) -> DbtCombinedGraph {
    let upstream: DbtGraphEdges = sort_targets(add_sqlbuild_edges(
        add_dbt_edges(DbtGraphEdges::default(), manifest),
        models,
    ));
    let downstream: DbtGraphEdges = sort_targets(inverted(&upstream));
    DbtCombinedGraph {
        upstream,
        downstream,
    }
}
