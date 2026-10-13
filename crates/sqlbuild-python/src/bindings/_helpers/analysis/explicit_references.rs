//! Compile's explicit-reference checks over plain project facts, run natively.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{FromPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_analysis::explicit_references::errors::ReferenceFailure;
use sqlbuild_analysis::explicit_references::main::check_explicit_references::check_explicit_references;
use sqlbuild_analysis::explicit_references::main::execution_gate_edges::execution_gate_edges;
use sqlbuild_analysis::explicit_references::models::{
    ExecutionGateEdges, ExecutionGateRequest, GateEdge, HookEdge, HookType, LiteralSql,
    ReferenceReport, ReferenceRequest, SqlOwner,
};
use sqlbuild_analysis::explicit_references::types::ResourceKey;
use sqlbuild_core::panics::main::native_failure::native_failure;
use sqlbuild_pysource::literal_sql::main::literal_sql_calls::literal_sql_calls;
use sqlbuild_pysource::literal_sql::models::FunctionSource;

use crate::bindings::_helpers::analysis::reference_facts::{ProjectFacts, project_facts, ref_keys};
use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::types::CompilerDetach;

const EXPLICIT_REFERENCES_CONTEXT: &str = "native explicit-reference checks";
const COMPILE_ERRORS_MODULE: &str = "sqlbuild.compiler.compile.exceptions";
const COMPILE_INPUT_ERROR: &str = "CompileInputError";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const REFERENCE_MODELS_MODULE: &str = "sqlbuild.compiler.references.models";
const CONTRACT_MODELS_MODULE: &str = "sqlbuild.spec.contracts.models";
const DIAGNOSTIC_PHASE: &str = "compile";
const DIAGNOSTIC_SEVERITY: &str = "error";

/// One Python SQL owner as Python collects it: the owner, its path order and literal SQL calls.
type OwnerInput<'py> = (Bound<'py, PyAny>, usize, Vec<(String, String, usize)>);

/// The project-wide settings of one explicit-reference check.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct ReportSettings {
    /// Whether the project keeps old-name views unless a model disables them.
    retains_old_names: bool,
    enforce_explicit: bool,
    explicit_help: String,
    /// The text Python substitutes for f-string values in literal SQL.
    placeholder: String,
}

/// Python's audit-gate, hook-read and Python-SQL checks as a `PythonSqlReferenceReport`.
#[pyfunction]
fn explicit_reference_report<'py>(
    py: Python<'py>,
    project: &Bound<'py, PyAny>,
    settings: ReportSettings,
    owners: Vec<OwnerInput<'py>>,
) -> PyResult<Bound<'py, PyAny>> {
    let facts: ProjectFacts = project_facts(project, settings.retains_old_names)?;
    let request = ReferenceRequest {
        enforce_explicit: settings.enforce_explicit,
        dialect: project.getattr("sql_analysis_dialect")?.extract()?,
        explicit_help: settings.explicit_help,
        placeholder: settings.placeholder,
        resources: facts.resources,
        models: facts.models,
        sources: facts.sources,
        seeds: facts.seeds,
        audits: facts.audits,
        hooks: facts.hooks,
        owners: owners
            .iter()
            .map(|(owner, path_order, literals)| sql_owner(owner, *path_order, literals))
            .collect::<PyResult<_>>()?,
    };
    match py
        .compiler_detach(|| Ok(check_explicit_references(&request)))
        .map_err(compiler_error)?
    {
        Ok(report) => python_report(py, &report, &owners),
        Err(ReferenceFailure::CompileInput(message)) => Err(PyErr::from_value(
            py.import(COMPILE_ERRORS_MODULE)?
                .getattr(COMPILE_INPUT_ERROR)?
                .call1((message,))?,
        )),
        Err(ReferenceFailure::UnknownDialect(message)) => Err(compiler_error(message)),
        Err(ReferenceFailure::Internal(reason)) => Err(compiler_error(native_failure(
            EXPLICIT_REFERENCES_CONTEXT,
            &reason,
        ))),
    }
}

fn sql_owner(
    owner: &Bound<'_, PyAny>,
    path_order: usize,
    literals: &[(String, String, usize)],
) -> PyResult<SqlOwner> {
    Ok(SqlOwner {
        label: owner.getattr("label")?.extract()?,
        kind: owner.getattr("kind")?.str()?.extract()?,
        path_order,
        own_refs: ref_keys(&owner.getattr("own_refs")?)?,
        upstream_loaders: owner
            .getattr("upstream_loader_by_source")?
            .call_method0("items")?
            .try_iter()?
            .map(|item| item?.extract())
            .collect::<PyResult<_>>()?,
        literals: literals
            .iter()
            .map(|(method, sql, line)| LiteralSql {
                method: method.clone(),
                sql: sql.clone(),
                line: *line,
            })
            .collect(),
    })
}

/// The report's diagnostics and unmatched relations as Python's compile models.
fn python_report<'py>(
    py: Python<'py>,
    report: &ReferenceReport,
    owners: &[OwnerInput<'py>],
) -> PyResult<Bound<'py, PyAny>> {
    let compile_models = py.import(COMPILE_MODELS_MODULE)?;
    let reference_models = py.import(REFERENCE_MODELS_MODULE)?;
    let source_location: Bound<'py, PyAny> = py
        .import(CONTRACT_MODELS_MODULE)?
        .getattr("SourceLocation")?;
    let path_class: Bound<'py, PyAny> = py.import("pathlib")?.getattr("Path")?;
    let compiler_diagnostic: Bound<'py, PyAny> = compile_models.getattr("CompilerDiagnostic")?;
    let mut diagnostics: Vec<Bound<'py, PyAny>> = Vec::with_capacity(report.diagnostics.len());
    for row in &report.diagnostics {
        let fields: Bound<'py, PyDict> = PyDict::new(py);
        fields.set_item("phase", DIAGNOSTIC_PHASE)?;
        fields.set_item("severity", DIAGNOSTIC_SEVERITY)?;
        fields.set_item("code", row.code)?;
        fields.set_item("message", &row.message)?;
        fields.set_item("resource_type", row.resource.as_ref().map(|key| &key.0))?;
        fields.set_item("resource_name", row.resource.as_ref().map(|key| &key.1))?;
        match &row.path {
            Some(path) => fields.set_item("path", path_class.call1((path,))?)?,
            None => fields.set_item("path", py.None())?,
        }
        match row.owner {
            Some(owner) => {
                let location: Bound<'py, PyDict> = PyDict::new(py);
                location.set_item("path", owners[owner].0.getattr("relative_path")?)?;
                location.set_item("line", row.line)?;
                location.set_item("column", 1)?;
                fields.set_item("location", source_location.call((), Some(&location))?)?;
            }
            None => fields.set_item("location", py.None())?,
        }
        fields.set_item("help", &row.help)?;
        diagnostics.push(compiler_diagnostic.call((), Some(&fields))?);
    }
    let literal_relation: Bound<'py, PyAny> = reference_models.getattr("LiteralSqlRelation")?;
    let relation_name: Bound<'py, PyAny> = reference_models.getattr("RelationName")?;
    let mut unmatched: Vec<Bound<'py, PyAny>> = Vec::with_capacity(report.unmatched.len());
    for row in &report.unmatched {
        let owner: &Bound<'py, PyAny> = &owners[row.owner].0;
        let relation: Bound<'py, PyDict> = PyDict::new(py);
        relation.set_item("name", &row.relation.name)?;
        relation.set_item("schema", &row.relation.schema)?;
        relation.set_item("database", &row.relation.database)?;
        let fields: Bound<'py, PyDict> = PyDict::new(py);
        fields.set_item("owner_label", owner.getattr("label")?)?;
        fields.set_item("owner_kind", owner.getattr("kind")?)?;
        fields.set_item("relative_path", owner.getattr("relative_path")?)?;
        fields.set_item("line", row.line)?;
        fields.set_item("method", &row.method)?;
        fields.set_item("relation", relation_name.call((), Some(&relation))?)?;
        unmatched.push(literal_relation.call((), Some(&fields))?);
    }
    let fields: Bound<'py, PyDict> = PyDict::new(py);
    fields.set_item("diagnostics", PyTuple::new(py, diagnostics)?)?;
    fields.set_item("unmatched", PyTuple::new(py, unmatched)?)?;
    compile_models
        .getattr("PythonSqlReferenceReport")?
        .call((), Some(&fields))
}

/// `(method, sql, line)` for each literal SQL call to the context in a dedented function source.
#[pyfunction]
fn python_literal_sql_calls(
    py: Python<'_>,
    source: &str,
    start_line: usize,
    placeholder: &str,
) -> Vec<(String, String, usize)> {
    let version = py.version_info();
    literal_sql_calls(&FunctionSource {
        text: source,
        start_line,
        placeholder,
        python_version: (version.major, version.minor),
    })
    .into_iter()
    .map(|call| (call.method, call.sql, call.line))
    .collect()
}

/// `(audit name, target, gated, read)` for one attached-audit ordering edge.
type GateRow = (String, ResourceKey, ResourceKey, ResourceKey);
/// `(hook name, gated, read, HookReadType value, path)` for one hook-read ordering edge.
type HookRow = (
    String,
    ResourceKey,
    ResourceKey,
    &'static str,
    Option<String>,
);

/// The attached-audit gate edges and hook-read edges of one project, in Python's order.
#[pyfunction]
fn native_execution_gate_edges(
    project: &Bound<'_, PyAny>,
) -> PyResult<(Vec<GateRow>, Vec<HookRow>)> {
    let facts: ProjectFacts = project_facts(project, false)?;
    let edges: ExecutionGateEdges = execution_gate_edges(&ExecutionGateRequest {
        resources: facts.resources,
        models: facts.models,
        audits: facts.audits,
        hooks: facts.hooks,
    });
    Ok((
        edges.audit_gates.into_iter().map(gate_row).collect(),
        edges.hook_reads.into_iter().map(hook_row).collect(),
    ))
}

fn gate_row(edge: GateEdge) -> GateRow {
    (edge.audit_name, edge.target, edge.gated, edge.read)
}

fn hook_row(edge: HookEdge) -> HookRow {
    let hook_type: &'static str = match edge.hook_type {
        HookType::Python => "Python",
        HookType::Sql => "SQL",
        HookType::InlineSql => "inline SQL",
    };
    (edge.hook_name, edge.gated, edge.read, hook_type, edge.path)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(explicit_reference_report, module)?)?;
    module.add_function(wrap_pyfunction!(python_literal_sql_calls, module)?)?;
    module.add_function(wrap_pyfunction!(native_execution_gate_edges, module)?)?;
    Ok(())
}
