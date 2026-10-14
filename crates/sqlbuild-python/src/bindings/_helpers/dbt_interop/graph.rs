//! The combined dbt and SQLBuild graph, `sqb dbt` selector resolution and dbt selector terms.

use std::collections::{HashMap, HashSet};

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyString, PyTuple};
use pyo3::{pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_core::dbt_graph::constants::PATH_SELECTOR_ERROR_CODE;
use sqlbuild_core::dbt_graph::errors::DbtSelectionError;
use sqlbuild_core::dbt_graph::main::build_dbt_combined_graph::build_dbt_combined_graph as build_graph;
use sqlbuild_core::dbt_graph::main::dbt_downstream_sqlbuild_models::dbt_downstream_sqlbuild_models;
use sqlbuild_core::dbt_graph::main::dbt_fqn_selector_term::dbt_fqn_selector_term as fqn_selector_term;
use sqlbuild_core::dbt_graph::main::resolve_dbt_selection::resolve_dbt_selection;
use sqlbuild_core::dbt_graph::models::{
    DbtCombinedGraph as CombinedGraph, DbtGraphEdges, DbtGraphManifest, DbtGraphManifestModel,
    DbtGraphProjectModel, DbtSelection, DbtSelectionRequest, DbtSelectorExpansion,
};
use sqlbuild_core::dbt_graph::types::DbtSelectorResolver;

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::dbt_interop::manifest::resolve_sqlbuild_model_dbt_refs;

const DBT_MODELS: &str = "sqlbuild.integrations.dbt.models";
const DBT_EXCEPTIONS: &str = "sqlbuild.integrations.dbt.exceptions";
const SELECTOR_EXPANSION_MODULE: &str =
    "sqlbuild.compiler.planner.main.selection.selector_expansion";
const MODEL_SELECTORS_MODULE: &str =
    "sqlbuild.compiler.planner.main.selection.sqlbuild_model_selectors";
const MODEL_RESOURCE_TYPE: &str = "model";
const SELECTION_OPTIONS: (&[&str], &[&str]) = (
    &["project", "graph", "select"],
    &["manifest", "exclude", "dbt_anchor_unique_ids_by_term"],
);

/// The combined downstream-only dbt and SQLBuild graph, keyed by `owner:type:name` stable IDs.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct DbtCombinedGraph {
    graph: CombinedGraph,
}

fn stable_edges<'py>(py: Python<'py>, edges: &DbtGraphEdges) -> PyResult<Bound<'py, PyDict>> {
    let result: Bound<'py, PyDict> = PyDict::new(py);
    for key in &edges.order {
        let targets: Vec<String> = edges
            .targets
            .get(key)
            .into_iter()
            .flatten()
            .map(|target| target.stable_id())
            .collect();
        result.set_item(key.stable_id(), PyTuple::new(py, targets)?)?;
    }
    Ok(result)
}

#[pymethods]
impl DbtCombinedGraph {
    /// Every node's stable ID.
    #[getter]
    fn nodes<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyFrozenSet>> {
        PyFrozenSet::new(
            py,
            self.graph.upstream.order.iter().map(|key| key.stable_id()),
        )
    }

    /// Upstream edges by stable ID.
    #[getter]
    fn upstream_deps<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        stable_edges(py, &self.graph.upstream)
    }

    /// Downstream edges by stable ID.
    #[getter]
    fn downstream_deps<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        stable_edges(py, &self.graph.downstream)
    }

    /// Sorted SQLBuild model names transitively downstream of any of the dbt models.
    fn downstream_sqlbuild_model_names<'py>(
        &self,
        py: Python<'py>,
        unique_ids: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let unique_ids: Vec<String> = texts(unique_ids)?;
        PyTuple::new(py, dbt_downstream_sqlbuild_models(&self.graph, &unique_ids))
    }
}

fn texts(values: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    values.try_iter()?.map(|value| value?.extract()).collect()
}

fn key_set(mapping: &Bound<'_, PyAny>) -> PyResult<HashSet<String>> {
    Ok(texts(mapping)?.into_iter().collect())
}

fn graph_manifest(manifest: &Bound<'_, PyAny>) -> PyResult<DbtGraphManifest> {
    let mut models: Vec<DbtGraphManifestModel> = Vec::new();
    for model in manifest
        .getattr("models_by_unique_id")?
        .call_method0("values")?
        .try_iter()?
    {
        let model: Bound<'_, PyAny> = model?;
        models.push(DbtGraphManifestModel {
            unique_id: model.getattr("unique_id")?.extract()?,
            name: model.getattr("name")?.extract()?,
            depends_on_nodes: texts(&model.getattr("depends_on_nodes")?)?,
        });
    }
    Ok(DbtGraphManifest {
        models,
        source_ids: key_set(&manifest.getattr("sources_by_unique_id")?)?,
        seed_ids: key_set(&manifest.getattr("seeds_by_unique_id")?)?,
    })
}

fn project_models<'py>(
    py: Python<'py>,
    project: &Bound<'py, PyAny>,
    manifest: &Bound<'py, PyAny>,
) -> PyResult<Vec<DbtGraphProjectModel>> {
    let mut refs_by_name: HashMap<String, Vec<String>> = HashMap::new();
    for pair in
        resolve_sqlbuild_model_dbt_refs(py, project.clone(), manifest.clone(), None)?.try_iter()?
    {
        let (model, dbt_model): (Bound<'py, PyAny>, Bound<'py, PyAny>) = pair?.extract()?;
        refs_by_name
            .entry(model.getattr("name")?.extract()?)
            .or_default()
            .push(dbt_model.getattr("unique_id")?.extract()?);
    }
    let mut models: Vec<DbtGraphProjectModel> = Vec::new();
    for model in project.getattr("models")?.try_iter()? {
        let model: Bound<'py, PyAny> = model?;
        let name: String = model.getattr("name")?.extract()?;
        let mut model_deps: Vec<String> = Vec::new();
        for dependency in model.getattr("deps")?.try_iter()? {
            let dependency: Bound<'py, PyAny> = dependency?;
            if dependency
                .getattr("resource_type")?
                .eq(MODEL_RESOURCE_TYPE)?
            {
                model_deps.push(dependency.getattr("name")?.extract()?);
            }
        }
        let dbt_ref_unique_ids: Vec<String> = refs_by_name.get(&name).cloned().unwrap_or_default();
        models.push(DbtGraphProjectModel {
            name,
            model_deps,
            dbt_ref_unique_ids,
        });
    }
    Ok(models)
}

/// Build the combined graph from a dbt manifest index and a compiled SQLBuild project.
#[pyfunction]
#[pyo3(signature = (*, manifest, project))]
fn build_dbt_combined_graph<'py>(
    py: Python<'py>,
    manifest: Bound<'py, PyAny>,
    project: Bound<'py, PyAny>,
) -> PyResult<DbtCombinedGraph> {
    let models: Vec<DbtGraphProjectModel> = project_models(py, &project, &manifest)?;
    Ok(DbtCombinedGraph {
        graph: build_graph(&graph_manifest(&manifest)?, &models),
    })
}

struct PlannerResolver<'py> {
    project: Bound<'py, PyAny>,
    split: Bound<'py, PyAny>,
    resolve: Bound<'py, PyAny>,
}

impl DbtSelectorResolver for PlannerResolver<'_> {
    type Error = PyErr;

    fn split(&self, term: &str) -> PyResult<DbtSelectorExpansion> {
        let parsed: Bound<'_, PyAny> = self.split.call1((term,))?;
        Ok(DbtSelectorExpansion {
            core: parsed.getattr("core")?.extract()?,
            upstream: parsed.getattr("upstream")?.is_truthy()?,
            downstream: parsed.getattr("downstream")?.is_truthy()?,
        })
    }

    fn model_names(&self, core: &str) -> PyResult<(Vec<String>, Option<String>)> {
        let py: Python<'_> = self.project.py();
        let (names, translated): (Bound<'_, PyAny>, Option<String>) = call_with(
            &self.resolve,
            &[
                ("project", self.project.clone()),
                ("term", PyString::new(py, core).into_any()),
            ],
        )?
        .extract()?;
        Ok((texts(&names)?, translated))
    }
}

fn selection_error(py: Python<'_>, error: DbtSelectionError<PyErr>) -> PyErr {
    match error {
        DbtSelectionError::Resolver(error) => error,
        DbtSelectionError::PathSelector(message) => {
            let raised = || -> PyResult<PyErr> {
                let keywords: Bound<'_, PyDict> = PyDict::new(py);
                keywords.set_item("code", PATH_SELECTOR_ERROR_CODE)?;
                let error: Bound<'_, PyAny> =
                    imported(py, DBT_EXCEPTIONS, "DbtInteropArgumentError")?
                        .call((message,), Some(&keywords))?;
                Ok(PyErr::from_value(error))
            };
            raised().unwrap_or_else(|failure| failure)
        }
    }
}

fn anchors(mapping: &Bound<'_, PyAny>) -> PyResult<HashMap<String, Vec<String>>> {
    let mut result: HashMap<String, Vec<String>> = HashMap::new();
    if mapping.is_none() {
        return Ok(result);
    }
    for item in mapping.call_method0("items")?.try_iter()? {
        let (term, unique_ids): (String, Bound<'_, PyAny>) = item?.extract()?;
        result.insert(term, texts(&unique_ids)?);
    }
    Ok(result)
}

fn manifest_models(manifest: &Bound<'_, PyAny>) -> PyResult<Option<Vec<(String, String)>>> {
    if manifest.is_none() {
        return Ok(None);
    }
    let models: Vec<(String, String)> = graph_manifest(manifest)?
        .models
        .into_iter()
        .map(|model| (model.unique_id, model.name))
        .collect();
    Ok(Some(models))
}

fn selection_result<'py>(py: Python<'py>, selection: DbtSelection) -> PyResult<Bound<'py, PyAny>> {
    let anchors_by_term: Bound<'py, PyDict> = PyDict::new(py);
    for (term, unique_ids) in selection.dbt_anchor_unique_ids_by_term {
        anchors_by_term.set_item(term, PyTuple::new(py, unique_ids)?)?;
    }
    let translations: Vec<Bound<'py, PyTuple>> = selection
        .path_translations
        .into_iter()
        .map(|(term, translated)| PyTuple::new(py, [term, translated]))
        .collect::<PyResult<_>>()?;
    call_with(
        &imported(py, DBT_MODELS, "DbtInteropSelectionResult")?,
        &[
            (
                "sqlbuild_model_names",
                PyTuple::new(py, selection.sqlbuild_model_names)?.into_any(),
            ),
            (
                "dbt_required_unique_ids",
                PyTuple::new(py, selection.dbt_required_unique_ids)?.into_any(),
            ),
            (
                "dbt_anchor_terms",
                PyTuple::new(py, selection.dbt_anchor_terms)?.into_any(),
            ),
            ("dbt_anchor_unique_ids_by_term", anchors_by_term.into_any()),
            (
                "path_translations",
                PyTuple::new(py, translations)?.into_any(),
            ),
        ],
    )
}

/// Resolve selected SQLBuild models and required dbt nodes from `sqb dbt` selectors.
#[pyfunction]
#[pyo3(signature = (**options))]
fn resolve_dbt_interop_sqlbuild_selection<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "resolve_dbt_interop_sqlbuild_selection",
        options,
        SELECTION_OPTIONS,
    )?;
    let manifest_models: Option<Vec<(String, String)>> =
        manifest_models(&arguments.value("manifest")?)?;
    let anchor_unique_ids_by_term: HashMap<String, Vec<String>> =
        anchors(&arguments.value("dbt_anchor_unique_ids_by_term")?)?;
    let select: Vec<String> = texts(&arguments.value("select")?)?;
    let exclude_terms: Bound<'py, PyAny> = arguments.value("exclude")?;
    let exclude: Vec<String> = if exclude_terms.is_none() {
        Vec::new()
    } else {
        texts(&exclude_terms)?
    };
    let request: DbtSelectionRequest<'_> = DbtSelectionRequest {
        select: &select,
        exclude: &exclude,
        anchor_unique_ids_by_term: &anchor_unique_ids_by_term,
        manifest_models: manifest_models.as_deref(),
    };
    let graph: Bound<'py, DbtCombinedGraph> = arguments.value("graph")?.cast_into()?;
    let resolver: PlannerResolver<'py> = PlannerResolver {
        project: arguments.value("project")?,
        split: imported(py, SELECTOR_EXPANSION_MODULE, "split_selector_expansion")?,
        resolve: imported(
            py,
            MODEL_SELECTORS_MODULE,
            "resolve_sqlbuild_model_selector_names",
        )?,
    };
    let selection: DbtSelection = resolve_dbt_selection(&resolver, &graph.get().graph, &request)
        .map_err(|error| selection_error(py, error))?;
    selection_result(py, selection)
}

/// The exact dbt FQN selector when the node has an FQN, else `fallback`.
#[pyfunction]
#[pyo3(signature = (*, fqn, fallback))]
fn dbt_fqn_selector_term(fqn: &Bound<'_, PyAny>, fallback: &str) -> PyResult<String> {
    Ok(fqn_selector_term(&texts(fqn)?, fallback))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<DbtCombinedGraph>()?;
    module.add_function(wrap_pyfunction!(build_dbt_combined_graph, module)?)?;
    module.add_function(wrap_pyfunction!(
        resolve_dbt_interop_sqlbuild_selection,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(dbt_fqn_selector_term, module)?)
}
