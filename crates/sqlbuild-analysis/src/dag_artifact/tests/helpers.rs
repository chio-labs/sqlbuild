use crate::assembly::project::types::ObjectKey;
use crate::dag_artifact::errors::DagArtifactError;
use crate::dag_artifact::main::build_dag_json::build_dag_json;
use crate::dag_artifact::models::{
    DagColumnInput, DagLoaderInput, DagPythonNodeInput, DagSourceEntryInput, DagSourceInput,
};
use crate::dag_artifact::tests::test_types::BuildDagJsonTestCase;
use crate::dag_artifact::types::DagValue;
use crate::graph::models::ProjectGraph;
use crate::python_values::main::text_key::text_key;

/// A `(resource type, name)` key.
pub(crate) fn key(kind: &str, name: &str) -> ObjectKey {
    (kind.to_owned(), name.to_owned())
}

/// A typed column without meta.
pub(crate) fn column(name: &str, data_type: &str) -> DagColumnInput {
    DagColumnInput {
        name: name.to_owned(),
        data_type: Some(data_type.to_owned()),
        nullable: None,
        description: None,
        meta: DagValue::Object(Vec::new()),
    }
}

/// A source in `raw` loaded by `loader`, when given.
pub(crate) fn source(name: &str, loader: Option<&str>, meta: DagValue) -> DagSourceInput {
    DagSourceInput {
        key: key("source", name),
        name: name.to_owned(),
        path: "sources/raw.yml".to_owned(),
        entry: DagSourceEntryInput {
            name: name.to_owned(),
            database: None,
            schema: Some("raw".to_owned()),
            table: None,
            description: None,
            loader: loader.map(str::to_owned),
            meta,
            columns: vec![column("id", "INTEGER")],
        },
    }
}

/// A loader at `destination` depending on `dependencies`.
pub(crate) fn loader(
    name: &str,
    destination: Option<&str>,
    dependencies: &[&str],
) -> DagLoaderInput {
    DagLoaderInput {
        name: name.to_owned(),
        path: "python/loaders.py".to_owned(),
        destination: destination.map(str::to_owned),
        columns: Vec::new(),
        dependency_names: dependencies.iter().map(|name| (*name).to_owned()).collect(),
    }
}

/// A Python node of `kind` reading the `sql_deps` keys.
pub(crate) fn python_node(kind: &str, name: &str, sql_deps: Vec<ObjectKey>) -> DagPythonNodeInput {
    DagPythonNodeInput {
        kind: kind.to_owned(),
        name: name.to_owned(),
        path: "python/nodes.py".to_owned(),
        description: None,
        tags: Vec::new(),
        group: None,
        meta: DagValue::Object(Vec::new()),
        asset: None,
        check_severity: (kind == "check").then(|| "error".to_owned()),
        sql_deps,
    }
}

/// The artifact JSON of a test case.
pub(crate) fn built(test_case: &BuildDagJsonTestCase) -> Result<String, DagArtifactError> {
    let graph: ProjectGraph = ProjectGraph {
        upstream: test_case.upstream.clone(),
        ..ProjectGraph::default()
    };
    build_dag_json(
        &graph,
        &test_case.project,
        test_case.python.as_ref(),
        "orders_project",
    )
}

/// Source meta with a `None` owner and the given team.
pub(crate) fn team_meta(value: DagValue) -> DagValue {
    DagValue::Object(vec![
        (text_key("owner"), DagValue::Null),
        (text_key("team"), value),
    ])
}
