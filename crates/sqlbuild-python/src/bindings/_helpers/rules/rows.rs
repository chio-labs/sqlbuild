//! Build and evaluate the built-in rules request natively from compiled-project rows.

use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::Mutex;

use pyo3::exceptions::PyOSError;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyRef, PyResult, Python,
};
use pyo3::types::{PyBytes, PyBytesMethods, PyDict, PyDictMethods};
use pyo3::{FromPyObject, pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_rules::engine::main::build_models::build_models;
use sqlbuild_rules::engine::main::evaluate_rows::evaluate_rows;
use sqlbuild_rules::engine::main::finalize_rows::finalize_rows;
use sqlbuild_rules::engine::main::project_model_rows::project_model_rows;
use sqlbuild_rules::errors::RowsError;
use sqlbuild_rules::models::{
    Declaration, DeclarationMember, EvaluateRequest, Fault, Model, ModelRow, ModelRowsContext,
    RowsEvaluation, RowsRequest, RulesConfig,
};

use crate::bindings::_helpers::boundary::panics::{compiler_guard, value_error};
use crate::bindings::_helpers::compiled_project::project::NativeCompiledProject;
use crate::bindings::_helpers::compiled_project::values::plain_value;
use crate::bindings::_helpers::rules::findings::{FindingClasses, finding_fault};
use crate::bindings::_helpers::rules::sql_test_objects::{scenario_fact, sql_test_fact};
use crate::bindings::types::CompilerDetach;

const LEFT_ARGUMENT: &str = "left";
const RIGHT_ARGUMENT: &str = "right";

type EvaluationRow<'py> = (
    Vec<Bound<'py, PyAny>>,
    Vec<String>,
    u64,
    u64,
    u64,
    u64,
    bool,
);

/// Name, relative path, members, value, value type and rendering of one declaration.
#[derive(FromPyObject)]
struct DeclarationRowPy<'py>(
    String,
    String,
    Vec<(String, Bound<'py, PyAny>)>,
    Bound<'py, PyAny>,
    Option<String>,
    Option<String>,
);

/// The request's project facts, which models, tests and scenarios are built beside.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct ProjectRowsPy<'py> {
    header_json: Bound<'py, PyBytes>,
    memo: Option<(String, String)>,
    sql_analysis_enabled: bool,
    include_type_proof: bool,
    attached_audit_targets: Vec<String>,
    public_enums: Vec<DeclarationRowPy<'py>>,
    public_constants: Vec<DeclarationRowPy<'py>>,
    initial_findings: Vec<Bound<'py, PyAny>>,
    types_equal: Bound<'py, PyAny>,
}

/// A natively built rules request held until it is evaluated once.
#[pyclass(module = "sqlbuild._native")]
struct NativeRulesRequest {
    request: Mutex<Option<RowsRequest>>,
}

#[pymethods]
impl NativeRulesRequest {
    /// The SQL test and scenario facts this request carries, as `{"sql_tests", "sql_scenarios"}` JSON.
    fn sql_facts_json(&self) -> PyResult<String> {
        let guard = self
            .request
            .lock()
            .map_err(|_| value_error("rules request lock is poisoned"))?;
        let rows: &RowsRequest = guard
            .as_ref()
            .ok_or_else(|| value_error("rules request was already evaluated"))?;
        serde_json::to_string(&serde_json::json!({
            "sql_tests": rows.request.sql_tests,
            "sql_scenarios": rows.request.sql_scenarios,
        }))
        .map_err(value_error)
    }
}

#[pyfunction]
fn build_rules_request<'py>(
    mut project: ProjectRowsPy<'py>,
    models: (PyRef<'py, NativeCompiledProject>, Vec<String>),
    sql_tests: Vec<Bound<'py, PyAny>>,
    scenarios: Vec<Bound<'py, PyAny>>,
) -> PyResult<NativeRulesRequest> {
    compiler_guard(|| {
        let mut request: EvaluateRequest =
            serde_json::from_slice(project.header_json.as_bytes()).map_err(value_error)?;
        request.sql_tests = sql_tests
            .iter()
            .map(sql_test_fact)
            .collect::<PyResult<_>>()?;
        request.sql_scenarios = scenarios
            .iter()
            .map(scenario_fact)
            .collect::<PyResult<_>>()?;
        request.public_enums = declarations(std::mem::take(&mut project.public_enums))?;
        request.public_constants = declarations(std::mem::take(&mut project.public_constants))?;
        request.initial_findings = project
            .initial_findings
            .iter()
            .map(finding_fault)
            .collect::<PyResult<_>>()?;
        let rows: Vec<ModelRow> =
            project_model_rows(models.0.facts(), &models.1).map_err(value_error)?;
        request.models = built_models(&project, &request, rows)?;
        let memo: Option<(String, PathBuf)> = project
            .memo
            .take()
            .map(|(identity, path)| (identity, PathBuf::from(path)));
        Ok(NativeRulesRequest {
            request: Mutex::new(Some(RowsRequest { request, memo })),
        })
    })
}

#[pyfunction]
fn evaluate_rules_request<'py>(
    py: Python<'py>,
    request: &Bound<'py, NativeRulesRequest>,
) -> PyResult<EvaluationRow<'py>> {
    let request: RowsRequest = request
        .borrow()
        .request
        .lock()
        .map_err(|_| value_error("rules request lock is poisoned"))?
        .take()
        .ok_or_else(|| value_error("rules request was already evaluated"))?;
    let evaluation: RowsEvaluation = py
        .compiler_detach(|| Ok(evaluate_rows(request)))
        .map_err(value_error)?
        .map_err(|error| match error {
            RowsError::Rules(message) => value_error(message),
            RowsError::Io(error) => PyOSError::new_err(error.to_string()),
        })?;
    let classes = FindingClasses::new(py)?;
    Ok((
        evaluation
            .faults
            .into_iter()
            .map(|fault| classes.finding_of_fault(fault, false))
            .collect::<PyResult<_>>()?,
        evaluation.selected_codes,
        evaluation.evaluated_models,
        evaluation.cache_hits,
        evaluation.cache_misses,
        evaluation.built_in_ms,
        evaluation.reused,
    ))
}

/// The findings one finalisation applies the exception policy to.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct FinalizeRowsPy<'py> {
    project_dir: String,
    config_json: Bound<'py, PyBytes>,
    evaluated_codes: Vec<String>,
    findings: Vec<Bound<'py, PyAny>>,
}

#[pyfunction]
fn finalize_rule_findings_rows<'py>(
    py: Python<'py>,
    request: FinalizeRowsPy<'py>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let config: RulesConfig = serde_json::from_slice(request.config_json.as_bytes())
        .map_err(|error| value_error(format!("invalid findings request: {error}")))?;
    let FinalizeRowsPy {
        project_dir,
        evaluated_codes,
        findings,
        ..
    } = request;
    let mut fixable: HashSet<(String, String, u64, u64, String)> = HashSet::new();
    let mut faults: Vec<Fault> = Vec::with_capacity(findings.len());
    for finding in &findings {
        let fault: Fault = finding_fault(finding)?;
        if finding.getattr("fixable")?.extract::<bool>()? {
            fixable.insert(fault_identity(&fault));
        }
        faults.push(fault);
    }
    let finalized: Vec<Fault> = py
        .compiler_detach(|| finalize_rows(project_dir, config, &evaluated_codes, faults))
        .map_err(value_error)?;
    let classes = FindingClasses::new(py)?;
    finalized
        .into_iter()
        .map(|fault| {
            let is_fixable: bool = fixable.contains(&fault_identity(&fault));
            classes.finding_of_fault(fault, is_fixable)
        })
        .collect()
}

/// `left=` and `right=`: the callback is `types_equal`, whose arguments are keyword-only.
fn type_arguments<'py>(py: Python<'py>, left: &str, right: &str) -> PyResult<Bound<'py, PyDict>> {
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    arguments.set_item(LEFT_ARGUMENT, left)?;
    arguments.set_item(RIGHT_ARGUMENT, right)?;
    Ok(arguments)
}

fn built_models(
    project: &ProjectRowsPy<'_>,
    request: &EvaluateRequest,
    rows: Vec<ModelRow>,
) -> PyResult<Vec<Model>> {
    let mut python_error: Option<PyErr> = None;
    let fallback = |left: &str, right: &str| -> Result<bool, String> {
        match type_arguments(project.types_equal.py(), left, right)
            .and_then(|arguments| project.types_equal.call((), Some(&arguments)))
            .and_then(|equal| equal.extract::<bool>())
        {
            Ok(equal) => Ok(equal),
            Err(error) => {
                let message: String = error.to_string();
                python_error = Some(error);
                Err(message)
            }
        }
    };
    let built: Result<Vec<Model>, String> = build_models(
        rows,
        ModelRowsContext {
            sql_analysis_enabled: project.sql_analysis_enabled,
            include_type_proof: project.include_type_proof,
            dialect: &request.dialect,
            attached_audit_targets: &project.attached_audit_targets,
            sql_tests: &request.sql_tests,
        },
        fallback,
    );
    built.map_err(|message| python_error.take().unwrap_or_else(|| value_error(message)))
}

fn declarations(rows: Vec<DeclarationRowPy<'_>>) -> PyResult<Vec<Declaration>> {
    rows.into_iter().map(declaration).collect()
}

fn declaration(row: DeclarationRowPy<'_>) -> PyResult<Declaration> {
    let DeclarationRowPy(name, relative_path, members, value, value_type, render_as) = row;
    Ok(Declaration {
        name,
        relative_path,
        members: members
            .into_iter()
            .map(declaration_member)
            .collect::<PyResult<_>>()?,
        value: Some(plain_value(&value)?).filter(|value| !value.is_null()),
        value_type,
        render_as,
    })
}

fn declaration_member((name, value): (String, Bound<'_, PyAny>)) -> PyResult<DeclarationMember> {
    Ok(DeclarationMember {
        name,
        value: plain_value(&value)?,
    })
}

fn fault_identity(fault: &Fault) -> (String, String, u64, u64, String) {
    (
        fault.code.clone(),
        fault.path.clone(),
        fault.line,
        fault.column,
        fault.message.clone(),
    )
}

/// A plain Python value as the rules request's JSON value, as orjson with `default=str` encodes it.
pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeRulesRequest>()?;
    module.add_function(wrap_pyfunction!(build_rules_request, module)?)?;
    module.add_function(wrap_pyfunction!(evaluate_rules_request, module)?)?;
    module.add_function(wrap_pyfunction!(finalize_rule_findings_rows, module)?)?;
    Ok(())
}
