//! The relation lineage index read from a project graph, and its Python selector views.

use std::collections::HashMap;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyTuple};
use sqlbuild_analysis::lineage_command::models::{LineageIndex, LineageKey, LineageNode};

const COMPILE_MODELS: &str = "sqlbuild.compiler.compile.models";
const GRAPH_MODELS: &str = "sqlbuild.compiler.graph.models";

/// A Python `CompiledObjectKey` as a lineage key.
pub(crate) fn lineage_key(key: &Bound<'_, PyAny>) -> PyResult<LineageKey> {
    Ok(LineageKey {
        resource_type: key.getattr("resource_type")?.str()?.extract()?,
        name: key.getattr("name")?.extract()?,
    })
}

/// Lineage keys of every Python key in `keys`.
pub(crate) fn lineage_keys(keys: &Bound<'_, PyAny>) -> PyResult<Vec<LineageKey>> {
    keys.try_iter()?.map(|key| lineage_key(&key?)).collect()
}

/// Python `CompiledObjectKey`s for lineage keys, one object per key.
pub(crate) struct PythonKeys<'py> {
    class: Bound<'py, PyAny>,
    made: HashMap<LineageKey, Bound<'py, PyAny>>,
}

impl<'py> PythonKeys<'py> {
    pub(crate) fn new(py: Python<'py>) -> PyResult<Self> {
        Ok(Self {
            class: py.import(COMPILE_MODELS)?.getattr("CompiledObjectKey")?,
            made: HashMap::new(),
        })
    }

    pub(crate) fn key(&mut self, key: &LineageKey) -> PyResult<Bound<'py, PyAny>> {
        if let Some(made) = self.made.get(key) {
            return Ok(made.clone());
        }
        let made: Bound<'py, PyAny> = self
            .class
            .call1((key.resource_type.as_str(), key.name.as_str()))?;
        self.made.insert(key.clone(), made.clone());
        Ok(made)
    }

    fn tuple(&mut self, keys: &[LineageKey]) -> PyResult<Bound<'py, PyTuple>> {
        let items: Vec<Bound<'py, PyAny>> = keys
            .iter()
            .map(|key| self.key(key))
            .collect::<PyResult<_>>()?;
        PyTuple::new(self.class.py(), items)
    }
}

fn ordered_edges(edges: &Bound<'_, PyAny>) -> PyResult<Vec<(LineageKey, Vec<LineageKey>)>> {
    let mut ordered: Vec<(LineageKey, Vec<LineageKey>)> = Vec::new();
    for item in edges.call_method0("items")?.try_iter()? {
        let (key, targets): (Bound<'_, PyAny>, Bound<'_, PyAny>) = item?.extract()?;
        ordered.push((lineage_key(&key)?, lineage_keys(&targets)?));
    }
    Ok(ordered)
}

fn optional_text(value: Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_none() {
        return Ok(None);
    }
    Ok(Some(value.str()?.extract()?))
}

/// A source entry's `database.schema.table`, as far as it is set.
fn source_relation_name(entry: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    let part = |name: &str| -> PyResult<Option<String>> {
        match entry.getattr(name) {
            Ok(value) if !value.is_none() => Ok(Some(value.extract()?)),
            _ => Ok(None),
        }
    };
    let Some(table) = part("table")? else {
        return Ok(None);
    };
    Ok(Some(match (part("database")?, part("schema")?) {
        (Some(database), Some(schema)) => format!("{database}.{schema}.{table}"),
        (_, Some(schema)) => format!("{schema}.{table}"),
        _ => table,
    }))
}

/// Display facts of every model, seed and source, models first as Python looks them up.
fn project_nodes(project: &Bound<'_, PyAny>) -> PyResult<HashMap<LineageKey, LineageNode>> {
    let mut nodes: HashMap<LineageKey, LineageNode> = HashMap::new();
    let mut add = |node: LineageNode| {
        nodes.entry(node.key.clone()).or_insert(node);
    };
    for model in project.getattr("models")?.try_iter()? {
        let model: Bound<'_, PyAny> = model?;
        add(LineageNode {
            key: lineage_key(&model.getattr("key")?)?,
            relative_path: optional_text(model.getattr("relative_path")?)?,
            qualified_name: optional_text(
                model.getattr("destination")?.getattr("qualified_name")?,
            )?,
        });
    }
    for seed in project.getattr("seeds")?.try_iter()? {
        let seed: Bound<'_, PyAny> = seed?;
        add(LineageNode {
            key: lineage_key(&seed.getattr("key")?)?,
            relative_path: optional_text(seed.getattr("seed_file")?.getattr("relative_path")?)?,
            qualified_name: optional_text(seed.getattr("destination")?.getattr("qualified_name")?)?,
        });
    }
    for source in project.getattr("sources")?.try_iter()? {
        let source: Bound<'_, PyAny> = source?;
        add(LineageNode {
            key: lineage_key(&source.getattr("key")?)?,
            relative_path: optional_text(source.getattr("source_file")?.getattr("relative_path")?)?,
            qualified_name: source_relation_name(&source.getattr("source_entry")?)?,
        });
    }
    Ok(nodes)
}

/// The lineage index of a compiled `ProjectGraph`; every named key has a node.
pub(crate) fn graph_index(graph: &Bound<'_, PyAny>) -> PyResult<LineageIndex> {
    let views: Bound<'_, PyAny> = graph.getattr("lineage_views")?;
    let mut all_keys: Vec<(String, LineageKey)> = Vec::new();
    for item in views
        .getattr("all_keys")?
        .call_method0("items")?
        .try_iter()?
    {
        let (name, key): (String, Bound<'_, PyAny>) = item?.extract()?;
        all_keys.push((name, lineage_key(&key)?));
    }
    let mut tags: Vec<(String, Vec<LineageKey>)> = Vec::new();
    for item in views
        .getattr("tag_index")?
        .call_method0("items")?
        .try_iter()?
    {
        let (tag, keys): (String, Bound<'_, PyAny>) = item?.extract()?;
        tags.push((tag, lineage_keys(&keys)?));
    }
    let mut paths: Vec<(LineageKey, String)> = Vec::new();
    for item in views
        .getattr("path_index")?
        .call_method0("items")?
        .try_iter()?
    {
        let (key, folder): (Bound<'_, PyAny>, String) = item?.extract()?;
        paths.push((lineage_key(&key)?, folder));
    }
    let mut nodes: HashMap<LineageKey, LineageNode> = project_nodes(&graph.getattr("project")?)?;
    for (_, key) in &all_keys {
        nodes.entry(key.clone()).or_insert_with(|| LineageNode {
            key: key.clone(),
            relative_path: None,
            qualified_name: None,
        });
    }
    Ok(LineageIndex {
        nodes,
        upstream: ordered_edges(&views.getattr("upstream_deps")?)?,
        downstream: ordered_edges(&views.getattr("downstream_deps")?)?,
        tags,
        paths,
        all_keys,
    })
}

/// `LineageGraphViews` of an index, for the planner's selector functions.
pub(crate) fn index_views<'py>(
    py: Python<'py>,
    index: &LineageIndex,
) -> PyResult<Bound<'py, PyAny>> {
    let mut keys: PythonKeys<'py> = PythonKeys::new(py)?;
    let edges = |pairs: &[(LineageKey, Vec<LineageKey>)],
                 keys: &mut PythonKeys<'py>|
     -> PyResult<Bound<'py, PyDict>> {
        let dict: Bound<'py, PyDict> = PyDict::new(py);
        for (key, targets) in pairs {
            dict.set_item(keys.key(key)?, keys.tuple(targets)?)?;
        }
        Ok(dict)
    };
    let upstream: Bound<'py, PyDict> = edges(&index.upstream, &mut keys)?;
    let downstream: Bound<'py, PyDict> = edges(&index.downstream, &mut keys)?;
    let tags: Bound<'py, PyDict> = PyDict::new(py);
    for (tag, tagged) in &index.tags {
        let items: Vec<Bound<'py, PyAny>> = tagged
            .iter()
            .map(|key| keys.key(key))
            .collect::<PyResult<_>>()?;
        tags.set_item(tag, PyFrozenSet::new(py, items)?)?;
    }
    let paths: Bound<'py, PyDict> = PyDict::new(py);
    for (key, folder) in &index.paths {
        paths.set_item(keys.key(key)?, folder)?;
    }
    let names: Bound<'py, PyDict> = PyDict::new(py);
    for (name, key) in &index.all_keys {
        names.set_item(name, keys.key(key)?)?;
    }
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item("upstream_deps", upstream)?;
    options.set_item("downstream_deps", downstream)?;
    options.set_item("tag_index", tags)?;
    options.set_item("path_index", paths)?;
    options.set_item("all_keys", names)?;
    py.import(GRAPH_MODELS)?
        .getattr("LineageGraphViews")?
        .call((), Some(&options))
}
