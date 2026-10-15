//! Compiled SQL tests and scenarios read into the native rules request's facts.

use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::PyString;
use sqlbuild_rules::models::{
    DirectTestResourceKind, SqlScenarioFact, SqlTestCteFact, SqlTestFact, SqlTestMode,
    SqlTestParameterFact, SqlTestParameterValueFact, TestedResource,
};

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::_helpers::compiled_project::records::plain_typed_value;
use crate::bindings::_helpers::compiled_project::values::plain_value;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";
const MODEL_PAYLOAD_CLASS: &str = "CompiledModelSqlTestPayload";
const DESCRIPTION_KEY: &str = "description";

fn posix(value: &Bound<'_, PyAny>) -> PyResult<String> {
    value.call_method0("as_posix")?.extract()
}

/// `primary` when it is truthy, otherwise `fallback`, as Python's `or` picks.
fn either<'py>(
    primary: Bound<'py, PyAny>,
    fallback: impl FnOnce() -> PyResult<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    if primary.is_truthy()? {
        Ok(primary)
    } else {
        fallback()
    }
}

fn names(owner: &Bound<'_, PyAny>, attribute: &str) -> PyResult<Vec<String>> {
    owner.getattr(attribute)?.extract()
}

fn ctes(payload: &Bound<'_, PyAny>, attribute: &str) -> PyResult<Vec<SqlTestCteFact>> {
    payload
        .getattr(attribute)?
        .try_iter()?
        .map(|cte| {
            let cte = cte?;
            Ok(SqlTestCteFact {
                name: cte.getattr("name")?.extract()?,
                sql: cte.getattr("sql_body")?.extract()?,
            })
        })
        .collect()
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

fn tested_resources(test: &Bound<'_, PyAny>) -> PyResult<Vec<TestedResource>> {
    test.getattr("tested_resources")?
        .try_iter()?
        .map(|resource| {
            let resource = resource?;
            let kind: String = resource.getattr("kind")?.getattr("value")?.extract()?;
            Ok(TestedResource {
                kind: tested_kind(&kind)?,
                name: resource.getattr("name")?.extract()?,
            })
        })
        .collect()
}

fn with_payload(test: &Bound<'_, PyAny>, mut fact: SqlTestFact) -> PyResult<SqlTestFact> {
    let payload: Bound<'_, PyAny> = test.getattr("payload")?;
    let model_payload: Bound<'_, PyAny> = test
        .py()
        .import(NATIVE_RECORDS_MODULE)?
        .getattr(MODEL_PAYLOAD_CLASS)?;
    if !payload.is_instance(&model_payload)? {
        return Ok(fact);
    }
    fact.authored_ctes = ctes(&payload, "authored_ctes")?;
    fact.expected_ctes = ctes(&payload, "expected_ctes")?;
    fact.assertion_ctes = ctes(&payload, "assertion_ctes")?;
    fact.has_macro_mocks = payload.getattr("macro_mocks")?.is_truthy()?;
    fact.has_model_query_overrides = payload.getattr("model_query_overrides")?.is_truthy()?;
    Ok(fact)
}

fn with_case(test: &Bound<'_, PyAny>, mut fact: SqlTestFact) -> PyResult<SqlTestFact> {
    let case_name: Option<String> = test.getattr("case_name")?.extract()?;
    let Some(case_name) = case_name else {
        return Ok(fact);
    };
    let mut schema: Vec<SqlTestParameterFact> = Vec::new();
    for parameter in test.getattr("parameter_schema")?.try_iter()? {
        let parameter = parameter?;
        schema.push(SqlTestParameterFact {
            name: parameter.getattr("name")?.extract()?,
            value_type: parameter
                .getattr("value_type")?
                .getattr("value")?
                .extract()?,
            nullable: parameter.getattr("nullable")?.extract()?,
        });
    }
    let types: HashMap<&str, &str> = schema
        .iter()
        .map(|parameter| (parameter.name.as_str(), parameter.value_type.as_str()))
        .collect();
    let mut parameters: Vec<SqlTestParameterValueFact> = Vec::new();
    for item in test.getattr("parameter_values")?.try_iter()? {
        let (name, value): (String, Bound<'_, PyAny>) = item?.extract()?;
        let value_type: String = types
            .get(name.as_str())
            .ok_or_else(|| PyValueError::new_err(format!("unknown test parameter {name}")))?
            .to_string();
        parameters.push(SqlTestParameterValueFact {
            name,
            value_type,
            value: plain_value(&plain_typed_value(&value)?)?,
        });
    }
    fact.parameters = parameters;
    fact.parameter_schema = schema;
    fact.parent_name = test.getattr("parent_name")?.extract()?;
    fact.case_name = Some(case_name);
    fact.case_index = test.getattr("case_index")?.extract()?;
    fact.case_fingerprint = test.getattr("case_fingerprint")?.extract()?;
    Ok(fact)
}

/// One compiled SQL test as the facts the built-in rules read.
pub(crate) fn sql_test_fact(test: &Bound<'_, PyAny>) -> PyResult<SqlTestFact> {
    let test_file: Bound<'_, PyAny> = test.getattr("test_file")?;
    let source_path: Bound<'_, PyAny> = either(test.getattr("source_path")?, || {
        test_file.getattr("relative_path")
    })?;
    let ownership_root: Bound<'_, PyAny> = either(test.getattr("ownership_root")?, || {
        test_file.getattr("ownership_root")
    })?;
    let block_index: Bound<'_, PyAny> = either(test.getattr("block_index")?, || {
        test.getattr("test_block")?.getattr("test_index")
    })?;
    let mode: String = test.getattr("mode")?.getattr("value")?.extract()?;
    let fact = SqlTestFact {
        source_path: posix(&source_path)?,
        ownership_root: posix(&ownership_root)?,
        block_index: block_index.extract()?,
        name: test.getattr("name")?.extract()?,
        explicit_name: test.getattr("explicit_name")?.extract()?,
        parent_name: None,
        case_name: None,
        case_index: None,
        case_fingerprint: None,
        parameter_schema: Vec::new(),
        parameters: Vec::new(),
        mode: test_mode(&mode)?,
        expected_model_names: names(test, "expected_model_names")?,
        assertion_names: names(test, "assertion_names")?,
        assertion_target_model_names: names(test, "assertion_target_model_names")?,
        target_model_names: names(test, "target_model_names")?,
        tested_resources: tested_resources(test)?,
        authored_ctes: Vec::new(),
        expected_ctes: Vec::new(),
        assertion_ctes: Vec::new(),
        has_macro_mocks: false,
        has_model_query_overrides: false,
        empty_input_only: false,
    };
    with_case(test, with_payload(test, fact)?)
}

/// One compiled SQL scenario as the facts the built-in rules read.
pub(crate) fn scenario_fact(scenario: &Bound<'_, PyAny>) -> PyResult<SqlScenarioFact> {
    let scenario_file: Bound<'_, PyAny> = scenario.getattr("scenario_file")?;
    let source_path: Bound<'_, PyAny> = either(scenario.getattr("source_path")?, || {
        scenario_file.getattr("relative_path")
    })?;
    let ownership_root: Bound<'_, PyAny> = either(scenario.getattr("ownership_root")?, || {
        scenario_file.getattr("ownership_root")
    })?;
    let header: Bound<'_, PyAny> = scenario_file
        .getattr("header_values")?
        .call_method1("get", (DESCRIPTION_KEY,))?;
    let description: Option<String> = if header.is_instance_of::<PyString>() {
        Some(header.extract()?)
    } else {
        None
    };
    Ok(SqlScenarioFact {
        source_path: posix(&source_path)?,
        ownership_root: posix(&ownership_root)?,
        name: scenario.getattr("name")?.extract()?,
        description,
        expected_model_names: names(scenario, "expected_model_names")?,
        assertion_names: names(scenario, "assertion_names")?,
        assertion_target_model_names: names(scenario, "assertion_target_model_names")?,
        target_model_names: names(scenario, "target_model_names")?,
    })
}
