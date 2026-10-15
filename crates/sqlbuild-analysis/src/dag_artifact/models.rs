//! The compiled project, Python node graph and authored values the DAG artifact is built from.

use std::collections::BTreeSet;

use crate::assembly::project::types::ObjectKey;
use crate::dag_artifact::types::{DagColumnLineage, DagValue};

/// One authored column: name, type, nullability, description and meta.
#[derive(Clone, Debug, PartialEq)]
pub struct DagColumnInput {
    pub name: String,
    pub data_type: Option<String>,
    pub nullable: Option<bool>,
    pub description: Option<String>,
    pub meta: DagValue,
}

/// A compiled relation location.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DagRelationInput {
    pub database: Option<String>,
    pub schema: Option<String>,
    pub name: Option<String>,
    pub qualified_name: Option<String>,
    pub logical_database: Option<String>,
    pub logical_schema: Option<String>,
}

/// A source declaration's entry.
#[derive(Clone, Debug, PartialEq)]
pub struct DagSourceEntryInput {
    pub name: String,
    pub database: Option<String>,
    pub schema: Option<String>,
    pub table: Option<String>,
    pub description: Option<String>,
    pub loader: Option<String>,
    pub meta: DagValue,
    pub columns: Vec<DagColumnInput>,
}

/// A compiled source.
#[derive(Clone, Debug, PartialEq)]
pub struct DagSourceInput {
    pub key: ObjectKey,
    pub name: String,
    /// `str(source_file.relative_path)`.
    pub path: String,
    pub entry: DagSourceEntryInput,
}

/// A discovered loader function.
#[derive(Clone, Debug, PartialEq)]
pub struct DagLoaderInput {
    pub name: String,
    pub path: String,
    /// The authored destination, if any.
    pub destination: Option<String>,
    pub columns: Vec<DagColumnInput>,
    /// Names of the project loaders this loader depends on, in dependency order.
    pub dependency_names: Vec<String>,
}

/// A compiled seed.
#[derive(Clone, Debug, PartialEq)]
pub struct DagSeedInput {
    pub key: ObjectKey,
    pub name: String,
    pub path: String,
    pub destination: DagRelationInput,
    pub description: Option<String>,
    pub tags: Vec<String>,
    pub meta: DagValue,
    pub columns: Vec<DagColumnInput>,
}

/// A compiled SQL or Python function.
#[derive(Clone, Debug, PartialEq)]
pub struct DagFunctionInput {
    pub name: String,
    pub path: String,
    pub destination: DagRelationInput,
    pub body_sql: String,
    pub language: String,
    pub tags: Vec<String>,
    pub returns: String,
    /// `(name, type)` of each returned column; a table function has at least one.
    pub return_columns: Vec<(String, Option<String>)>,
    pub arguments: Vec<(String, String)>,
}

/// The parts of a model's schema entry the artifact reads.
#[derive(Clone, Debug, PartialEq)]
pub struct DagModelSchemaInput {
    pub description: Option<String>,
    pub tags: Vec<String>,
    pub meta: DagValue,
    pub columns: Vec<DagColumnInput>,
}

/// A compiled model.
#[derive(Clone, Debug, PartialEq)]
pub struct DagModelInput {
    pub key: ObjectKey,
    pub name: String,
    pub path: String,
    pub destination: DagRelationInput,
    pub authored_sql: String,
    pub schema: Option<DagModelSchemaInput>,
    /// `str()` of each configured tag, when the `tags` config value is a list or tuple.
    pub config_tags: Option<Vec<String>>,
    /// `str()` of the `materialized` config value, `view` by default.
    pub materialization: String,
    pub inferred_columns: Option<Vec<(String, Option<String>)>>,
}

/// A Python asset's declared columns and column lineage.
#[derive(Clone, Debug, PartialEq)]
pub struct DagPythonAssetInput {
    pub columns: Vec<DagColumnInput>,
    /// Column to `(upstream node, upstream column)` references, when declared.
    pub column_lineage: Option<DagColumnLineage>,
}

/// A discovered Python node.
#[derive(Clone, Debug, PartialEq)]
pub struct DagPythonNodeInput {
    pub kind: String,
    pub name: String,
    pub path: String,
    pub description: Option<String>,
    pub tags: Vec<String>,
    pub group: Option<String>,
    /// `node.meta or {}`.
    pub meta: DagValue,
    pub asset: Option<DagPythonAssetInput>,
    /// The `AuditSeverity` value of a check's severity.
    pub check_severity: Option<String>,
    /// Graph keys of the SQL resources the node reads.
    pub sql_deps: Vec<ObjectKey>,
}

/// The discovered Python node graph.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct DagPythonGraphInput {
    pub nodes: Vec<DagPythonNodeInput>,
    /// `(upstream name, downstream name)` of each dependency edge.
    pub dependency_edges: Vec<(String, String)>,
    /// Each name's node kind, as `nodes_by_name` maps it.
    pub kinds_by_name: Vec<(String, String)>,
}

/// One case of a parameterized SQL test.
#[derive(Clone, Debug, PartialEq)]
pub struct DagSqlTestCaseInput {
    pub case_name: String,
    pub block_index: Option<i64>,
    pub parent_name: Option<String>,
    pub case_index: Option<i64>,
    pub case_fingerprint: Option<String>,
    /// `(name, value type, nullable)` of each declared parameter.
    pub parameter_schema: Vec<(String, String, bool)>,
    /// `(name, value)` of each bound parameter, decimals already as text.
    pub parameters: Vec<(String, DagValue)>,
}

/// A compiled SQL test.
#[derive(Clone, Debug, PartialEq)]
pub struct DagSqlTestInput {
    pub key: ObjectKey,
    pub name: String,
    /// `str(test_file.relative_path)`.
    pub path: String,
    /// `(source_path or test_file.relative_path).as_posix()`.
    pub source_path: String,
    pub mode: String,
    pub scope_deps: Vec<ObjectKey>,
    pub case: Option<DagSqlTestCaseInput>,
}

/// A compiled audit.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DagAuditInput {
    pub key: ObjectKey,
    pub name: String,
    pub path: String,
    pub scope_deps: Vec<ObjectKey>,
    pub attached_target_kind: Option<String>,
    pub attached_target_name: Option<String>,
    pub attached_column_name: Option<String>,
    pub severity: Option<String>,
}

/// A compiled SQL scenario.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DagScenarioInput {
    pub key: ObjectKey,
    pub name: String,
    pub path: String,
    pub expected_model_names: Vec<String>,
    pub authored_cte_names: Vec<String>,
    pub assertion_names: Vec<String>,
    /// Source, ref, seed and dbt ref fixture names, each group in authored order.
    pub fixture_names: [Vec<String>; 4],
}

/// The project's compiled resources and target defaults.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct DagProjectInput {
    pub sources: Vec<DagSourceInput>,
    pub loaders: Vec<DagLoaderInput>,
    pub seeds: Vec<DagSeedInput>,
    pub functions: Vec<DagFunctionInput>,
    pub models: Vec<DagModelInput>,
    pub sql_tests: Vec<DagSqlTestInput>,
    pub audits: Vec<DagAuditInput>,
    pub scenarios: Vec<DagScenarioInput>,
    pub target_database: Option<String>,
    pub target_schema: Option<String>,
}

/// One DAG artifact node as the Dagster selection reads it.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DagSelectionNode {
    pub id: String,
    pub name: String,
    pub kind: String,
    pub path: Option<String>,
    pub tags: Vec<String>,
}

/// One DAG artifact check: its name, id and checked asset ids.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DagSelectionCheck {
    pub name: String,
    pub id: String,
    pub checked_asset_ids: Vec<String>,
}

/// The DAG artifact's nodes, `(from, to)` edges and checks.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DagSelectionGraph {
    pub nodes: Vec<DagSelectionNode>,
    pub edges: Vec<(String, String)>,
    pub checks: Vec<DagSelectionCheck>,
}

/// One DAG artifact node as orchestrator asset projection reads it.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DagProjectionNode {
    pub id: String,
    pub kind: String,
}

/// One DAG artifact check as orchestrator check projection reads it.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DagProjectionCheck {
    pub kind: String,
    pub checked_asset_ids: Vec<String>,
}

/// The DAG artifact's nodes, `(from, to)` edges and checks, in artifact order.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DagProjectionGraph {
    pub nodes: Vec<DagProjectionNode>,
    pub edges: Vec<(String, String)>,
    pub checks: Vec<DagProjectionCheck>,
}

/// Which nodes become orchestrator assets and which upstream nodes they depend on.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct AssetProjectionPolicy {
    /// Node kinds the orchestrator owns as assets.
    pub asset_kinds: BTreeSet<String>,
    /// Upstream nodes of other kinds are left out of an asset's dependencies.
    pub upstream_asset_kinds_only: bool,
}

/// One asset node and the nodes it depends on, as indexes into the graph's nodes.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct AssetNodePlan {
    pub node: usize,
    pub upstream: Vec<usize>,
}

/// Which check kinds a check definition exposes.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CheckKindFilter {
    pub excluded: BTreeSet<String>,
    /// When set, only these kinds are exposed.
    pub required: Option<BTreeSet<String>>,
}

/// One check, whether its kind is exposed, and the nodes it checks as graph indexes.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CheckPlan {
    pub check: usize,
    pub included: bool,
    pub nodes: Vec<usize>,
}

/// How an asset's orchestrator kinds follow from its node kind and materialization.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct AssetSpecKindPolicy {
    pub model_kind: String,
    pub view_materialization: String,
    /// Node kinds reported as their own orchestrator kind.
    pub direct_kinds: BTreeSet<String>,
}

/// The node lookup and edge indexes every selector token resolves against.
#[derive(Debug)]
pub(crate) struct DagSelectionIndex<'a> {
    pub(crate) graph: &'a DagSelectionGraph,
    pub(crate) nodes: std::collections::BTreeMap<&'a str, &'a DagSelectionNode>,
    pub(crate) upstream: crate::dag_artifact::_helpers::selection::Adjacency,
    pub(crate) downstream: crate::dag_artifact::_helpers::selection::Adjacency,
}
