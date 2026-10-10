//! Assemble compiled SQL test facts from compile inputs' own objects, without a JSON request.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{FromPyObject, PyErr, pyfunction, wrap_pyfunction};
use sqlbuild_analysis::compiler::main::sql_test_assembly::assemble_sql_test_batch;
use sqlbuild_analysis::compiler::models::{
    AssembledSqlTestFacts, SqlTestAssemblyBatch, SqlTestAssemblyFailure, SqlTestAssemblyModel,
    SqlTestAssemblyModelPayload, SqlTestAssemblyOutcome, SqlTestAssemblyPayload,
    SqlTestAssemblyReference, SqlTestAssemblyTest, SqlTestCte, SqlTestParameterValue,
};

use sqlbuild_core::panics::main::native_failure::native_failure;

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;
use crate::bindings::types::CompilerDetach;

const MACRO_TOKEN: char = '@';
const INPUT_FAILURE: &str = "input";
const INTERNAL_FAILURE: &str = "internal";
const DECIMAL_OVERFLOW: &str = "decimal_overflow";
const SQL_TEST_ASSEMBLY_CONTEXT: &str = "native SQL test assembly";

/// `(line, column, end line, end column, message, help)` of one P013 diagnostic.
type DiagnosticRow = (usize, usize, usize, usize, String, String);
/// `(name, scope deps, target models, case fingerprint, diagnostic resource, diagnostics)`.
type FactsRow = (
    String,
    Vec<(&'static str, String)>,
    Vec<String>,
    Option<String>,
    String,
    Vec<DiagnosticRow>,
);
/// The test's facts, and the `(kind, message)` of the error its assembly raises, if any: kind
/// `input` (no facts), `internal` (no facts) or `decimal_overflow` (after the facts).
type AssemblyRow = (Option<FactsRow>, Option<(&'static str, String)>);

/// The Python assembly request: the project's model inputs and the SQL test inputs.
#[derive(FromPyObject)]
struct AssemblyRequest<'py> {
    #[pyo3(attribute)]
    model_inputs: Vec<Bound<'py, PyAny>>,
    #[pyo3(attribute)]
    test_inputs: Vec<Bound<'py, PyAny>>,
    #[pyo3(attribute)]
    lexical_syntax: LexicalSyntaxInput,
}

/// Each test input's assembled facts, or the error its assembly raises.
#[pyfunction]
fn assemble_compiled_sql_tests(
    py: Python<'_>,
    request: AssemblyRequest<'_>,
) -> PyResult<Vec<AssemblyRow>> {
    let batch = SqlTestAssemblyBatch {
        models: request
            .model_inputs
            .iter()
            .map(assembly_model)
            .collect::<PyResult<_>>()?,
        tests: request
            .test_inputs
            .iter()
            .map(assembly_test)
            .collect::<PyResult<_>>()?,
        lexical_syntax: request.lexical_syntax.into(),
    };
    let outcomes = py
        .compiler_detach(|| Ok(assemble_sql_test_batch(&batch)))
        .map_err(value_error)?;
    Ok(outcomes.into_iter().map(assembly_row).collect())
}

fn assembly_model(model: &Bound<'_, PyAny>) -> PyResult<SqlTestAssemblyModel> {
    let macro_deps: Vec<String> = model.getattr("macro_deps")?.extract()?;
    let unscanned_macro_source = if macro_deps.is_empty() {
        Some(model.getattr("macro_source_sql")?.extract::<String>()?)
            .filter(|sql| sql.contains(MACRO_TOKEN))
    } else {
        None
    };
    Ok(SqlTestAssemblyModel {
        name: model
            .getattr("model_file")?
            .getattr("file_path")?
            .getattr("stem")?
            .extract()?,
        macro_deps,
        unscanned_macro_source,
        references: model
            .getattr("references")?
            .try_iter()?
            .map(|reference| {
                let reference = reference?;
                Ok(SqlTestAssemblyReference {
                    kind: reference.getattr("ref_kind")?.extract()?,
                    name: reference.getattr("ref_name")?.extract()?,
                    package: reference.getattr("ref_package")?.extract()?,
                })
            })
            .collect::<PyResult<_>>()?,
    })
}

fn assembly_test(test: &Bound<'_, PyAny>) -> PyResult<SqlTestAssemblyTest> {
    let test_file = test.getattr("test_file")?;
    let test_block = test.getattr("test_block")?;
    let relative_path = test_file.getattr("relative_path")?;
    let payload = test.getattr("payload")?;
    let payload = if payload.hasattr("actual_cte")? {
        SqlTestAssemblyPayload::Direct {
            mode: payload.getattr("mode")?.extract()?,
            tested_resource_names: payload.getattr("tested_resource_names")?.extract()?,
        }
    } else {
        SqlTestAssemblyPayload::Model(SqlTestAssemblyModelPayload {
            authored_ctes: ctes(&payload, "authored_ctes")?,
            expected_ctes: ctes(&payload, "expected_ctes")?,
            assertion_ctes: ctes(&payload, "assertion_ctes")?,
            expected_model_names: payload.getattr("expected_model_names")?.extract()?,
            assertion_target_model_names: payload
                .getattr("assertion_target_model_names")?
                .extract()?,
            reference_target_model_names: payload
                .getattr("reference_target_model_names")?
                .extract()?,
            mock_model_names: payload.getattr("mock_model_names")?.extract()?,
        })
    };
    Ok(SqlTestAssemblyTest {
        block_name: test_block.getattr("name")?.extract()?,
        file_stem: test_file.getattr("file_path")?.getattr("stem")?.extract()?,
        relative_path: relative_path.call_method0("as_posix")?.extract()?,
        relative_stem: relative_path.getattr("stem")?.extract()?,
        contents: test_file.getattr("contents")?.extract()?,
        block_sql: test_block.getattr("sql_body")?.extract()?,
        block_index: test_block.getattr("test_index")?.extract()?,
        sql_body: test.getattr("sql_body")?.extract()?,
        case_name: test.getattr("case_name")?.extract()?,
        parameter_schema: test
            .getattr("parameter_schema")?
            .try_iter()?
            .map(|parameter| {
                let parameter = parameter?;
                Ok((
                    parameter.getattr("name")?.extract()?,
                    parameter.getattr("value_type")?.extract()?,
                    parameter.getattr("nullable")?.extract()?,
                ))
            })
            .collect::<PyResult<_>>()?,
        parameter_values: test
            .getattr("parameter_values")?
            .try_iter()?
            .map(|entry| {
                let (name, value): (String, Bound<'_, PyAny>) = entry?.extract()?;
                Ok((name, parameter_value(&value)?))
            })
            .collect::<PyResult<_>>()?,
        payload,
    })
}

fn ctes(owner: &Bound<'_, PyAny>, attribute: &str) -> PyResult<Vec<SqlTestCte>> {
    owner
        .getattr(attribute)?
        .try_iter()?
        .map(|value| {
            let value = value?;
            Ok(SqlTestCte {
                name: value.getattr("name")?.extract()?,
                sql_body: value.getattr("sql_body")?.extract()?,
            })
        })
        .collect()
}

/// One `SqlValue`, read by its logical kind; decimals keep `as_tuple()`'s digits.
fn parameter_value(value: &Bound<'_, PyAny>) -> PyResult<SqlTestParameterValue> {
    let kind: String = value.getattr("logical_type")?.getattr("kind")?.extract()?;
    let payload = value.getattr("value")?;
    Ok(match kind.as_str() {
        "string" => SqlTestParameterValue::String(payload.extract()?),
        "integer" => SqlTestParameterValue::Integer(payload.extract()?),
        "boolean" => SqlTestParameterValue::Boolean(payload.extract()?),
        "float" => SqlTestParameterValue::Float(payload.extract()?),
        "decimal" => {
            let (sign, digits, exponent): (u8, Vec<u8>, i64) =
                payload.call_method0("as_tuple")?.extract()?;
            SqlTestParameterValue::Decimal {
                negative: sign == 1,
                digits,
                exponent,
            }
        }
        "null" => SqlTestParameterValue::Null,
        "list" => SqlTestParameterValue::List(parameter_values(&payload)?),
        "set" => SqlTestParameterValue::Set(parameter_values(&payload)?),
        "object" => SqlTestParameterValue::Object(
            payload
                .try_iter()?
                .map(|entry| {
                    let (key, item): (String, Bound<'_, PyAny>) = entry?.extract()?;
                    Ok((key, parameter_value(&item)?))
                })
                .collect::<PyResult<_>>()?,
        ),
        other => {
            return Err(PyErr::new::<PyValueError, _>(format!(
                "unknown SQL value kind {other:?}"
            )));
        }
    })
}

fn parameter_values(items: &Bound<'_, PyAny>) -> PyResult<Vec<SqlTestParameterValue>> {
    items
        .try_iter()?
        .map(|item| parameter_value(&item?))
        .collect()
}

fn assembly_row(outcome: SqlTestAssemblyOutcome) -> AssemblyRow {
    match outcome {
        SqlTestAssemblyOutcome::Assembled(facts) => (Some(facts_row(facts)), None),
        SqlTestAssemblyOutcome::FingerprintOverflow(facts) => (
            Some(facts_row(facts)),
            Some((DECIMAL_OVERFLOW, String::new())),
        ),
        SqlTestAssemblyOutcome::Failed(SqlTestAssemblyFailure::Input(message)) => {
            (None, Some((INPUT_FAILURE, message)))
        }
        SqlTestAssemblyOutcome::Failed(SqlTestAssemblyFailure::Internal(reason)) => (
            None,
            Some((
                INTERNAL_FAILURE,
                native_failure(SQL_TEST_ASSEMBLY_CONTEXT, &reason),
            )),
        ),
    }
}

fn facts_row(facts: AssembledSqlTestFacts) -> FactsRow {
    (
        facts.name,
        facts.scope_deps,
        facts.target_model_names,
        facts.case_fingerprint,
        facts.diagnostic_resource_name,
        facts
            .diagnostics
            .into_iter()
            .map(|diagnostic| {
                (
                    diagnostic.line,
                    diagnostic.column,
                    diagnostic.end_line,
                    diagnostic.end_column,
                    diagnostic.message,
                    diagnostic.help,
                )
            })
            .collect(),
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(assemble_compiled_sql_tests, module)?)?;
    Ok(())
}
