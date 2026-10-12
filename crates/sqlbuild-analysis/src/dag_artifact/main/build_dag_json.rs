//! The static DAG artifact JSON of a compiled project and its Python node graph.

use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};
use std::collections::HashMap;

use crate::dag_artifact::_helpers::checks::checks;
use crate::dag_artifact::_helpers::edges::edges;
use crate::dag_artifact::_helpers::nodes::{
    function_node, loader_node, model_node, python_node, seed_node, source_node, sources_by_loader,
};
use crate::dag_artifact::_helpers::values::{drop_none, encoded, integer, object, text};
use crate::dag_artifact::constants::{DAG_INDENT, DAG_VERSION, LOADER_KIND};
use crate::dag_artifact::errors::DagArtifactError;
use crate::dag_artifact::models::{DagProjectInput, DagPythonGraphInput};
use crate::dag_artifact::types::DagValue;
use crate::graph::models::ProjectGraph;

fn nodes(
    project: &DagProjectInput,
    python: Option<&DagPythonGraphInput>,
) -> Result<Vec<DagValue>, DagArtifactError> {
    let declared: HashMap<&str, &str> = sources_by_loader(project);
    let mut nodes: Vec<DagValue> = project.sources.iter().map(source_node).collect();
    for loader in &project.loaders {
        if !declared.contains_key(loader.name.as_str()) {
            nodes.push(loader_node(loader, project)?);
        }
    }
    nodes.extend(project.seeds.iter().map(seed_node));
    nodes.extend(project.functions.iter().map(function_node));
    nodes.extend(project.models.iter().map(model_node));
    if let Some(python) = python {
        nodes.extend(
            python
                .nodes
                .iter()
                .filter(|node| node.kind != LOADER_KIND)
                .map(python_node),
        );
    }
    Ok(nodes)
}

/// `json.dumps` of the artifact with `None` and empty optional fields dropped, indented by two.
pub fn build_dag_json(
    graph: &ProjectGraph,
    project: &DagProjectInput,
    python: Option<&DagPythonGraphInput>,
    project_name: &str,
) -> Result<String, DagArtifactError> {
    let artifact: DagValue = object(vec![
        ("version", integer(DAG_VERSION)),
        ("project_name", text(project_name)),
        ("nodes", DagValue::Array(nodes(project, python)?)),
        ("edges", edges(graph, project, python)),
        ("checks", checks(project, python)?),
    ]);
    let value: JsonValue = encoded(drop_none(artifact))?;
    dumps(
        &value,
        &JsonDialect::Stdlib(StdlibJsonOptions::new(Some(DAG_INDENT))),
    )
    .map_err(DagArtifactError::Emit)
}
