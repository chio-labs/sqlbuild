//! The compiled project graph and selector resolution, held natively for Python's graph users.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_analysis::assembly::project::types::ObjectKey;
use sqlbuild_analysis::graph::errors::SelectorError;
use sqlbuild_analysis::graph::main::build_project_graph::build_project_graph;
use sqlbuild_analysis::graph::main::build_resources::build_resources;
use sqlbuild_analysis::graph::main::edge_keys::edge_keys;
use sqlbuild_analysis::graph::main::graph_from_indexes::graph_from_indexes;
use sqlbuild_analysis::graph::main::match_selector::match_selector;
use sqlbuild_analysis::graph::main::model_layer_count::model_layer_count;
use sqlbuild_analysis::graph::main::parse_selector::parse_selector;
use sqlbuild_analysis::graph::main::resolve_selector_tokens::resolve_selector_tokens;
use sqlbuild_analysis::graph::main::resolve_selectors::resolve_selectors;
use sqlbuild_analysis::graph::main::selector_name_help::selector_name_help;
use sqlbuild_analysis::graph::models::{
    BuildResources, EdgeDirection, GraphIndexes, GraphResource, ParsedSelector, ProjectGraph,
};

use crate::bindings::_helpers::boundary::panics::compiler_guard;

const KIND_SELECTOR: &str = "kind";
const PATH_SELECTOR: &str = "path";

/// `(key, deps, tags, model folder)`.
type ResourceRow = (ObjectKey, Vec<ObjectKey>, Vec<String>, Option<String>);
type Edges = Vec<(ObjectKey, Vec<ObjectKey>)>;
/// `(names, upstream, downstream, tags, paths)` in Python's dict order.
type IndexesRow = (
    Vec<(String, ObjectKey)>,
    Edges,
    Edges,
    Vec<(String, Vec<ObjectKey>)>,
    Vec<(ObjectKey, String)>,
);
/// `PlannerInputError`'s `(code, message, help)`.
type FailureRow = (&'static str, String, Option<String>);
/// The keys, or the `PlannerInputError` Python raises instead.
type KeysOutcome = (Option<Vec<ObjectKey>>, Option<FailureRow>);
/// `("kind", kind, value, upstream, downstream)` or `("path", start, end, upstream, downstream)`.
type ParsedRow = (&'static str, String, String, bool, bool);

/// A project graph: lineage edges, tag, path and name indexes, and selector resolution.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeProjectGraph {
    graph: ProjectGraph,
}

fn dependency_edges(key: &ObjectKey, deps: &[ObjectKey]) -> Vec<(ObjectKey, ObjectKey)> {
    deps.iter().map(|dep| (dep.clone(), key.clone())).collect()
}

fn outcome(result: Result<Vec<ObjectKey>, SelectorError>) -> KeysOutcome {
    match result {
        Ok(keys) => (Some(keys), None),
        Err(error) => (None, Some(failure(error))),
    }
}

fn failure(error: SelectorError) -> FailureRow {
    (error.code, error.message, error.help)
}

impl NativeProjectGraph {
    /// Wrap a graph another native stage built, such as project assembly.
    pub(crate) fn new(graph: ProjectGraph) -> Self {
        Self { graph }
    }
}

#[pymethods]
impl NativeProjectGraph {
    /// Build the indexes from resources in project order: models, sources, seeds, functions.
    #[staticmethod]
    fn from_resources(resources: Vec<ResourceRow>) -> PyResult<Self> {
        compiler_guard(|| {
            let resources: Vec<GraphResource> = resources
                .into_iter()
                .map(|(key, deps, tags, folder)| GraphResource {
                    key,
                    deps,
                    tags,
                    folder,
                })
                .collect();
            Ok(Self::new(build_project_graph(&resources)))
        })
    }

    /// Wrap indexes a caller already built, such as the planner's.
    #[staticmethod]
    fn from_indexes(indexes: IndexesRow) -> PyResult<Self> {
        compiler_guard(|| {
            let (names, upstream, downstream, tags, paths) = indexes;
            Ok(Self::new(graph_from_indexes(GraphIndexes {
                names,
                upstream,
                downstream,
                tags,
                paths,
            })))
        })
    }

    /// `(names, upstream, downstream, tags, paths)` for Python's `ProjectGraph`.
    fn indexes(&self) -> IndexesRow {
        let graph: &ProjectGraph = &self.graph;
        (
            graph.names.clone(),
            graph.upstream.clone(),
            graph.downstream.clone(),
            graph.tags.clone(),
            graph.paths.clone(),
        )
    }

    /// The key's direct upstream lineage keys, in authored dependency order.
    fn upstream(&self, key: ObjectKey) -> Vec<ObjectKey> {
        edge_keys(&self.graph, &key, EdgeDirection::Upstream).to_vec()
    }

    /// The key's direct downstream keys, sorted by `(resource type, name)`.
    fn downstream(&self, key: ObjectKey) -> Vec<ObjectKey> {
        edge_keys(&self.graph, &key, EdgeDirection::Downstream).to_vec()
    }

    /// Every selectable key, in project order with later same-name resources replacing earlier.
    fn keys(&self) -> Vec<ObjectKey> {
        self.graph
            .names
            .iter()
            .map(|(_, key)| key.clone())
            .collect()
    }

    /// `(selector name, key)` in project order.
    fn names(&self) -> Vec<(String, ObjectKey)> {
        self.graph.names.clone()
    }

    /// Every lineage edge as `(dependency, dependent)`, in upstream order.
    fn edges(&self) -> Vec<(ObjectKey, ObjectKey)> {
        self.graph
            .upstream
            .iter()
            .flat_map(|(key, deps)| dependency_edges(key, deps))
            .collect()
    }

    /// The compile report's execution layer count over models.
    fn model_layer_count(&self) -> usize {
        model_layer_count(&self.graph)
    }

    /// `--select` minus `--exclude`, plus the functions they need to build.
    fn resolve(&self, select: Vec<String>, exclude: Vec<String>) -> PyResult<KeysOutcome> {
        compiler_guard(|| Ok(outcome(resolve_selectors(&self.graph, &select, &exclude))))
    }

    /// The keys selector tokens match, without build resources.
    fn tokens(&self, selectors: Vec<String>) -> PyResult<KeysOutcome> {
        compiler_guard(|| Ok(outcome(resolve_selector_tokens(&self.graph, &selectors))))
    }

    /// The keys one `kind:value` selector names before `+` expansion.
    fn matched(&self, kind: &str, value: &str) -> PyResult<KeysOutcome> {
        compiler_guard(|| Ok(outcome(match_selector(&self.graph, kind, value))))
    }

    /// The selected keys plus the functions and seeds Python adds to build them.
    fn build_resources(
        &self,
        selected: Vec<ObjectKey>,
        include: (bool, bool, bool),
    ) -> PyResult<Vec<ObjectKey>> {
        compiler_guard(|| {
            let (upstream_functions, upstream_seeds, downstream_functions) = include;
            Ok(build_resources(
                &self.graph,
                &selected,
                BuildResources {
                    upstream_functions,
                    upstream_seeds,
                    downstream_functions,
                },
            ))
        })
    }
}

/// One selector token parsed, or the `PlannerInputError` Python raises.
#[pyfunction]
fn parse_project_selector(raw: &str) -> (Option<ParsedRow>, Option<FailureRow>) {
    match parse_selector(raw) {
        Ok(ParsedSelector::Kind {
            kind,
            value,
            upstream,
            downstream,
        }) => (
            Some((KIND_SELECTOR, kind, value, upstream, downstream)),
            None,
        ),
        Ok(ParsedSelector::Path {
            start,
            end,
            upstream,
            downstream,
        }) => (
            Some((PATH_SELECTOR, start, end, upstream, downstream)),
            None,
        ),
        Err(error) => (None, Some(failure(error))),
    }
}

/// The "did you mean" help for an unknown selector name, if any.
#[pyfunction]
fn project_selector_name_help(value: &str, candidates: Vec<String>) -> Option<String> {
    selector_name_help(value, candidates.iter().map(String::as_str).collect())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeProjectGraph>()?;
    module.add_function(wrap_pyfunction!(parse_project_selector, module)?)?;
    module.add_function(wrap_pyfunction!(project_selector_name_help, module)?)
}
