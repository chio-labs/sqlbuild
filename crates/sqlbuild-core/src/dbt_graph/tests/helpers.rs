use std::collections::{HashMap, HashSet};

use crate::dbt_graph::errors::DbtSelectionError;
use crate::dbt_graph::main::build_dbt_combined_graph::build_dbt_combined_graph;
use crate::dbt_graph::main::resolve_dbt_selection::resolve_dbt_selection;
use crate::dbt_graph::models::{
    DbtCombinedGraph, DbtGraphEdges, DbtGraphManifest, DbtGraphManifestModel, DbtGraphProjectModel,
    DbtSelection, DbtSelectionRequest, DbtSelectorExpansion,
};
use crate::dbt_graph::tests::test_types::NameResolver;
use crate::dbt_graph::types::DbtSelectorResolver;

fn texts(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

/// Manifest: stg <- raw source and seed; int <- stg; a second `dup` name in two packages.
pub(super) fn manifest() -> DbtGraphManifest {
    let model = |unique_id: &str, name: &str, deps: &[&str]| DbtGraphManifestModel {
        unique_id: unique_id.to_owned(),
        name: name.to_owned(),
        depends_on_nodes: texts(deps),
    };
    DbtGraphManifest {
        models: vec![
            model(
                "model.a.stg",
                "stg",
                &["source.a.raw.orders", "seed.a.codes", "x"],
            ),
            model("model.a.int", "int", &["model.a.stg", "model.a.stg"]),
            model("model.a.dup", "dup", &[]),
            model("model.b.dup", "dup", &[]),
        ],
        source_ids: HashSet::from(["source.a.raw.orders".to_owned()]),
        seed_ids: HashSet::from(["seed.a.codes".to_owned()]),
    }
}

/// Project: fact <- dbt int; mart <- fact and an unknown model; local alone.
pub(super) fn project() -> Vec<DbtGraphProjectModel> {
    let model = |name: &str, deps: &[&str], refs: &[&str]| DbtGraphProjectModel {
        name: name.to_owned(),
        model_deps: texts(deps),
        dbt_ref_unique_ids: texts(refs),
    };
    vec![
        model("fact", &[], &["model.a.int"]),
        model("mart", &["fact", "missing"], &[]),
        model("local", &[], &[]),
    ]
}

pub(super) fn graph() -> DbtCombinedGraph {
    build_dbt_combined_graph(&manifest(), &project())
}

/// Edges as stable IDs in node order.
pub(super) fn stable_edges(edges: &DbtGraphEdges) -> Vec<(String, Vec<String>)> {
    edges
        .order
        .iter()
        .map(|key| {
            let targets: Vec<String> = edges
                .targets
                .get(key)
                .into_iter()
                .flatten()
                .map(|target| target.stable_id())
                .collect();
            (key.stable_id(), targets)
        })
        .collect()
}

impl DbtSelectorResolver for NameResolver {
    type Error = String;

    fn split(&self, term: &str) -> Result<DbtSelectorExpansion, String> {
        let core: &str = term.trim_matches('+');
        if core.is_empty() {
            return Err(format!("selector '{term}' has no name"));
        }
        Ok(DbtSelectorExpansion {
            core: core.to_owned(),
            upstream: term.starts_with('+'),
            downstream: term.ends_with('+'),
        })
    }

    fn model_names(&self, core: &str) -> Result<(Vec<String>, Option<String>), String> {
        if let Some(path) = core.strip_prefix("path:") {
            let translated: String = path.replace('\\', "/");
            let changed: Option<String> =
                (translated != path).then(|| format!("path:{translated}"));
            return Ok((Vec::new(), changed));
        }
        Ok((
            self.names
                .iter()
                .filter(|name| **name == core)
                .map(|name| (*name).to_owned())
                .collect(),
            None,
        ))
    }
}

/// Resolve selectors against the helper graph with a name-only resolver.
pub(super) fn select(
    select: &[&str],
    exclude: &[&str],
    anchors: &[(&str, Vec<&str>)],
) -> Result<DbtSelection, DbtSelectionError<String>> {
    let anchors: HashMap<String, Vec<String>> = anchors
        .iter()
        .map(|(term, ids)| ((*term).to_owned(), texts(ids)))
        .collect();
    let manifest_models: Vec<(String, String)> = manifest()
        .models
        .into_iter()
        .map(|model| (model.unique_id, model.name))
        .collect();
    let (select, exclude): (Vec<String>, Vec<String>) = (texts(select), texts(exclude));
    let request: DbtSelectionRequest<'_> = DbtSelectionRequest {
        select: &select,
        exclude: &exclude,
        anchor_unique_ids_by_term: &anchors,
        manifest_models: Some(&manifest_models),
    };
    let resolver: NameResolver = NameResolver {
        names: vec!["fact", "mart", "local"],
    };
    resolve_dbt_selection(&resolver, &graph(), &request)
}

/// A selection with the given sorted models and dbt nodes.
pub(super) fn selection(sqlbuild: &[&str], dbt: &[&str]) -> DbtSelection {
    DbtSelection {
        sqlbuild_model_names: texts(sqlbuild),
        dbt_required_unique_ids: texts(dbt),
        ..DbtSelection::default()
    }
}
