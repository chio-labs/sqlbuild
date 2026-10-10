//! Build and evaluate the built-in rules request natively from compiled-project rows.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Mutex;

use pyo3::exceptions::{PyOSError, PyValueError};
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyRef, PyResult, Python,
};
use pyo3::types::{PyBytes, PyBytesMethods, PyDict, PyDictMethods};
use pyo3::{FromPyObject, pyclass, pyfunction, wrap_pyfunction};
use sqlbuild_rules::engine::main::build_models::build_models;
use sqlbuild_rules::engine::main::evaluate_rows::evaluate_rows;
use sqlbuild_rules::engine::main::finalize_rows::finalize_rows;
use sqlbuild_rules::engine::main::project_model_rows::project_model_rows;
use sqlbuild_rules::errors::RowsError;
use sqlbuild_rules::models::{
    Declaration, DeclarationMember, DirectTestResourceKind, EvaluateRequest, Fault, Model,
    ModelRow, ModelRowsContext, RowsEvaluation, RowsRequest, RulesConfig, SqlScenarioFact,
    SqlTestCteFact, SqlTestFact, SqlTestMode, SqlTestParameterFact, SqlTestParameterValueFact,
    TestedResource,
};

use crate::bindings::_helpers::boundary::panics::{compiler_guard, value_error};
use crate::bindings::_helpers::compiled_project::project::NativeCompiledProject;
use crate::bindings::_helpers::compiled_project::values::plain_value;
use crate::bindings::types::CompilerDetach;

const LEFT_ARGUMENT: &str = "left";
const RIGHT_ARGUMENT: &str = "right";

type FaultRow = (bool, String, String, u64, u64, String, String);
type CteRow = (String, String);
type ModelTestPayloadPy = (Vec<CteRow>, Vec<CteRow>, Vec<CteRow>, bool, bool);
type TestNamesRow = (Vec<String>, Vec<String>, Vec<String>, Vec<String>);
type BuiltCounts = (usize, usize, usize);
type EvaluationRow = (Vec<FaultRow>, Vec<String>, u64, u64, u64, u64, bool);

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

#[derive(FromPyObject)]
struct SqlTestRowPy<'py>(
    String,
    String,
    u64,
    String,
    Option<String>,
    String,
    TestNamesRow,
    Vec<(String, String)>,
    Option<ModelTestPayloadPy>,
    Option<SqlTestCaseRowPy<'py>>,
);

#[derive(FromPyObject)]
struct SqlTestCaseRowPy<'py>(
    Option<String>,
    String,
    Option<u64>,
    Option<String>,
    Vec<(String, String, bool)>,
    Vec<(String, Bound<'py, PyAny>)>,
);

#[derive(FromPyObject)]
struct ScenarioRowPy(
    String,
    String,
    String,
    Option<String>,
    Vec<String>,
    Vec<String>,
    Vec<String>,
    Vec<String>,
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
    initial_findings: Vec<FaultRow>,
    types_equal: Bound<'py, PyAny>,
}

/// A natively built rules request held until it is evaluated once.
#[pyclass(module = "sqlbuild._native")]
struct NativeRulesRequest {
    request: Mutex<Option<RowsRequest>>,
}

#[pyfunction]
fn build_rules_request<'py>(
    mut project: ProjectRowsPy<'py>,
    models: (PyRef<'py, NativeCompiledProject>, Vec<String>),
    sql_tests: Vec<SqlTestRowPy<'py>>,
    scenarios: Vec<ScenarioRowPy>,
) -> PyResult<(NativeRulesRequest, BuiltCounts)> {
    compiler_guard(|| {
        let mut request: EvaluateRequest =
            serde_json::from_slice(project.header_json.as_bytes()).map_err(value_error)?;
        request.sql_tests = sql_tests
            .into_iter()
            .map(sql_test)
            .collect::<PyResult<_>>()?;
        request.sql_scenarios = scenarios.into_iter().map(scenario).collect();
        request.public_enums = declarations(std::mem::take(&mut project.public_enums))?;
        request.public_constants = declarations(std::mem::take(&mut project.public_constants))?;
        request.initial_findings = std::mem::take(&mut project.initial_findings)
            .into_iter()
            .map(fault)
            .collect();
        let rows: Vec<ModelRow> =
            project_model_rows(models.0.facts(), &models.1).map_err(value_error)?;
        request.models = built_models(&project, &request, rows)?;
        let counts: BuiltCounts = (
            request.models.len(),
            request.sql_tests.len(),
            request.sql_scenarios.len(),
        );
        let memo: Option<(String, PathBuf)> = project
            .memo
            .take()
            .map(|(identity, path)| (identity, PathBuf::from(path)));
        Ok((
            NativeRulesRequest {
                request: Mutex::new(Some(RowsRequest { request, memo })),
            },
            counts,
        ))
    })
}

#[pyfunction]
fn evaluate_rules_request(
    py: Python<'_>,
    request: &Bound<'_, NativeRulesRequest>,
) -> PyResult<EvaluationRow> {
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
    Ok((
        evaluation.faults.into_iter().map(fault_row).collect(),
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
    findings: Vec<FaultRow>,
}

#[pyfunction]
fn finalize_rule_findings_rows(
    py: Python<'_>,
    request: FinalizeRowsPy<'_>,
) -> PyResult<Vec<FaultRow>> {
    let config: RulesConfig = serde_json::from_slice(request.config_json.as_bytes())
        .map_err(|error| value_error(format!("invalid findings request: {error}")))?;
    let FinalizeRowsPy {
        project_dir,
        evaluated_codes,
        findings,
        ..
    } = request;
    let faults: Vec<Fault> = findings.into_iter().map(fault).collect();
    let finalized: Vec<Fault> = py
        .compiler_detach(|| finalize_rows(project_dir, config, &evaluated_codes, faults))
        .map_err(value_error)?;
    Ok(finalized.into_iter().map(fault_row).collect())
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

fn sql_test(row: SqlTestRowPy<'_>) -> PyResult<SqlTestFact> {
    let SqlTestRowPy(
        source_path,
        ownership_root,
        block_index,
        name,
        explicit_name,
        mode,
        (expected_model_names, assertion_names, assertion_target_model_names, target_model_names),
        tested_resources,
        model_payload,
        case,
    ) = row;
    let (authored_ctes, expected_ctes, assertion_ctes, has_macro_mocks, has_model_query_overrides) =
        model_payload.unwrap_or_default();
    let mut fact = SqlTestFact {
        source_path,
        ownership_root,
        block_index,
        name,
        explicit_name,
        parent_name: None,
        case_name: None,
        case_index: None,
        case_fingerprint: None,
        parameter_schema: Vec::new(),
        parameters: Vec::new(),
        mode: test_mode(&mode)?,
        expected_model_names,
        assertion_names,
        assertion_target_model_names,
        target_model_names,
        tested_resources: tested_resources
            .into_iter()
            .map(|(kind, name)| {
                Ok(TestedResource {
                    kind: tested_kind(&kind)?,
                    name,
                })
            })
            .collect::<PyResult<_>>()?,
        authored_ctes: ctes(authored_ctes),
        expected_ctes: ctes(expected_ctes),
        assertion_ctes: ctes(assertion_ctes),
        has_macro_mocks,
        has_model_query_overrides,
        empty_input_only: false,
    };
    if let Some(SqlTestCaseRowPy(
        parent_name,
        case_name,
        case_index,
        case_fingerprint,
        schema,
        values,
    )) = case
    {
        let types: HashMap<&str, &str> = schema
            .iter()
            .map(|(name, value_type, _)| (name.as_str(), value_type.as_str()))
            .collect();
        fact.parameters = values
            .into_iter()
            .map(|(name, value)| {
                let value_type: String = types
                    .get(name.as_str())
                    .ok_or_else(|| PyValueError::new_err(format!("unknown test parameter {name}")))?
                    .to_string();
                Ok(SqlTestParameterValueFact {
                    name,
                    value_type,
                    value: plain_value(&value)?,
                })
            })
            .collect::<PyResult<_>>()?;
        fact.parameter_schema = schema
            .into_iter()
            .map(|(name, value_type, nullable)| SqlTestParameterFact {
                name,
                value_type,
                nullable,
            })
            .collect();
        fact.parent_name = parent_name;
        fact.case_name = Some(case_name);
        fact.case_index = case_index;
        fact.case_fingerprint = case_fingerprint;
    }
    Ok(fact)
}

fn ctes(rows: Vec<CteRow>) -> Vec<SqlTestCteFact> {
    rows.into_iter()
        .map(|(name, sql)| SqlTestCteFact { name, sql })
        .collect()
}

fn scenario(row: ScenarioRowPy) -> SqlScenarioFact {
    let ScenarioRowPy(
        source_path,
        ownership_root,
        name,
        description,
        expected_model_names,
        assertion_names,
        assertion_target_model_names,
        target_model_names,
    ) = row;
    SqlScenarioFact {
        source_path,
        ownership_root,
        name,
        description,
        expected_model_names,
        assertion_names,
        assertion_target_model_names,
        target_model_names,
    }
}

fn test_mode(value: &str) -> PyResult<SqlTestMode> {
    match value {
        "model" => Ok(SqlTestMode::Model),
        "macro" => Ok(SqlTestMode::Macro),
        "udf" => Ok(SqlTestMode::Udf),
        "table_fn" => Ok(SqlTestMode::TableFn),
        _ => Err(value_error(format!("unknown SQL test mode {value}"))),
    }
}

fn tested_kind(value: &str) -> PyResult<DirectTestResourceKind> {
    match value {
        "macro" => Ok(DirectTestResourceKind::Macro),
        "udf" => Ok(DirectTestResourceKind::Udf),
        "table_fn" => Ok(DirectTestResourceKind::TableFn),
        _ => Err(value_error(format!("unknown tested resource kind {value}"))),
    }
}

fn fault((unevaluated, code, path, line, column, message, remediation): FaultRow) -> Fault {
    Fault {
        unevaluated,
        code,
        path,
        line,
        column,
        message,
        remediation,
    }
}

fn fault_row(fault: Fault) -> FaultRow {
    (
        fault.unevaluated,
        fault.code,
        fault.path,
        fault.line,
        fault.column,
        fault.message,
        fault.remediation,
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
