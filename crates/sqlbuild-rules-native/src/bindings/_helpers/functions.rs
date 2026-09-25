//! Register the versioned Python boundary for the native Rules engine.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{
    Bound, IntoPyObject, Py, PyAny, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyTuple};
use pyo3::{FromPyObject, pyfunction, wrap_pyfunction};

use crate::configuration::main::load;
use crate::constants::API_VERSION;
use crate::engine::main::evaluate;
use crate::models::CatalogueResponse;
use crate::rules::main::{catalogue, selected_codes};

const SKILL_OWNER: &str = "sqlbuild";
const SKILL_IDENTITY: &str = "sqlbuild-rules";

fn value_error(error: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(error.to_string())
}

#[pyfunction]
fn evaluate_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| evaluate::evaluate_json(request_json))
        .map_err(value_error)
}

#[pyfunction]
fn lint_sql_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| crate::sql_lint::main::engine::lint_json(request_json))
        .map_err(value_error)
}

#[pyfunction]
fn finalize_rule_findings_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| crate::engine::main::finalize::finalize_findings_json(request_json))
        .map_err(value_error)
}

/// One SQL lint preparation request, read from a Python mapping.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct LintPreparationRequest {
    expanded: String,
    before_expansion: String,
    prior_sites: Vec<usize>,
    dialect: String,
}

#[pyfunction]
fn prepare_lint_sql(
    py: Python<'_>,
    request: LintPreparationRequest,
) -> PyResult<Option<crate::sql_lint::types::PreparedSql>> {
    py.detach(|| {
        crate::sql_lint::main::preparation::prepare(
            &request.expanded,
            &request.before_expansion,
            &request.prior_sites,
            &request.dialect,
        )
    })
    .map_err(value_error)
}

#[pyfunction]
fn lint_backtick_identifiers(dialect: &str) -> bool {
    crate::sql_lint::main::backtick_identifiers::backtick_identifiers(dialect)
}

#[pyfunction]
fn lint_sql_batch_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| crate::sql_lint::main::batch_engine::lint_batch_json(request_json))
        .map_err(pyo3::exceptions::PyValueError::new_err)
}

#[pyfunction]
fn format_sql_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| crate::sql_lint::main::formatter::format_json(request_json))
        .map_err(value_error)
}

#[pyfunction]
fn format_sql_batch_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| crate::sql_lint::main::batch_formatter::format_batch_json(request_json))
        .map_err(value_error)
}

#[pyfunction(name = "validate_sql_with_schema_json")]
fn schema_validation_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| crate::semantic_validation::main::validation_json(request_json))
        .map_err(value_error)
}

#[pyfunction(name = "validate_sql_with_schemas_json")]
fn schema_validations_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| crate::semantic_validation::main::validations_json(request_json))
        .map_err(value_error)
}

#[pyfunction]
fn analyze_sql_uses_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| crate::semantic_usage::main::analyze_json(request_json))
        .map_err(value_error)
}

#[pyfunction]
fn analyze_queries_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| crate::query_analysis::main::analyze::analyze_json(request_json))
        .map_err(value_error)
}

#[pyfunction]
fn analyze_project_queries_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| crate::query_analysis::main::analyze_project::analyze_project_json(request_json))
        .map_err(value_error)
}

#[pyfunction]
fn analyze_project_queries_compact_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| {
        crate::query_analysis::main::analyze_project_compact::analyze_project_compact_json(
            request_json,
        )
    })
    .map_err(value_error)
}

#[pyfunction]
fn render_sql_test_comparisons_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| crate::compiler::main::sql_test_rendering::render_json(request_json))
        .map_err(value_error)
}

#[pyfunction]
fn plan_and_render_sql_tests_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| crate::compiler::main::sql_test_planning::plan_and_render_json(request_json))
        .map_err(value_error)
}

#[pyfunction]
fn resolve_sql_test_chains_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| {
        crate::compiler::main::sql_test_chain_resolution::resolve_chains_json(request_json)
    })
    .map_err(value_error)
}

#[pyfunction]
fn render_sql_test_difference_sample_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| {
        crate::compiler::main::sql_test_difference_sampling::render_difference_sample_json(
            request_json,
        )
    })
    .map_err(value_error)
}

#[pyfunction]
fn extract_sql_tests_json(py: Python<'_>, request_json: &str) -> PyResult<String> {
    py.detach(|| crate::compiler::main::sql_test_extraction::extract_batch_json(request_json))
        .map_err(value_error)
}

fn authored_value_to_python(
    py: Python<'_>,
    value: crate::compiler::models::AuthoredValue,
) -> PyResult<Py<PyAny>> {
    use crate::compiler::models::AuthoredValue;

    match value {
        AuthoredValue::Null => Ok(py.None()),
        AuthoredValue::Boolean(value) => {
            Ok(value.into_pyobject(py)?.to_owned().unbind().into_any())
        }
        AuthoredValue::BareWord(value) => {
            marker_to_python(py, "word", value.into_pyobject(py)?.unbind().into_any())
        }
        AuthoredValue::String(value) => Ok(value.into_pyobject(py)?.unbind().into_any()),
        AuthoredValue::List(values) => {
            let projected = values
                .into_iter()
                .map(|item| authored_value_to_python(py, item))
                .collect::<PyResult<Vec<_>>>()?;
            Ok(PyList::new(py, projected)?.unbind().into_any())
        }
        AuthoredValue::Map(values) => map_to_python(py, values),
        AuthoredValue::Set(values) => marker_to_python(
            py,
            "set",
            authored_value_to_python(py, AuthoredValue::List(values))?,
        ),
        AuthoredValue::Tuple(values) => marker_to_python(
            py,
            "tuple",
            authored_value_to_python(py, AuthoredValue::List(values))?,
        ),
        AuthoredValue::TypedConstant(values) => {
            marker_to_python(py, "constant", map_to_python(py, values)?)
        }
        AuthoredValue::InlineSqlHook(statement) => marker_to_python(
            py,
            "inline_sql",
            statement.into_pyobject(py)?.unbind().into_any(),
        ),
        AuthoredValue::NamedSqlHook(name, kwargs) => hook_marker(py, "sql", name, kwargs),
        AuthoredValue::PythonHook(name, kwargs) => hook_marker(py, "python", name, kwargs),
    }
}

fn map_to_python(
    py: Python<'_>,
    values: Vec<(String, crate::compiler::models::AuthoredValue)>,
) -> PyResult<Py<PyAny>> {
    let result = PyDict::new(py);
    for (key, value) in values {
        result.set_item(key, authored_value_to_python(py, value)?)?;
    }
    Ok(result.unbind().into_any())
}

fn marker_to_python(py: Python<'_>, kind: &str, value: Py<PyAny>) -> PyResult<Py<PyAny>> {
    Ok(
        PyTuple::new(py, [kind.into_pyobject(py)?.unbind().into_any(), value])?
            .unbind()
            .into_any(),
    )
}

fn hook_marker(
    py: Python<'_>,
    kind: &str,
    name: String,
    kwargs: Vec<(String, crate::compiler::models::AuthoredValue)>,
) -> PyResult<Py<PyAny>> {
    let payload = PyTuple::new(
        py,
        [
            name.into_pyobject(py)?.unbind().into_any(),
            map_to_python(py, kwargs)?,
        ],
    )?;
    marker_to_python(py, kind, payload.unbind().into_any())
}

fn optional_authored_value_to_python(
    py: Python<'_>,
    value: Option<crate::compiler::models::AuthoredValue>,
) -> PyResult<Option<Py<PyAny>>> {
    value
        .map(|item| authored_value_to_python(py, item))
        .transpose()
}

type ParsedModelHeader = (
    Option<Py<PyAny>>,
    Option<Vec<(String, usize, usize)>>,
    Option<String>,
);

#[pyfunction]
fn parse_model_headers(py: Python<'_>, headers: Vec<String>) -> PyResult<Vec<ParsedModelHeader>> {
    let parsed = py
        .detach(|| crate::compiler::main::model_header_parsing::parse_batch(&headers))
        .map_err(value_error)?;
    parsed
        .into_iter()
        .map(|(value, offsets, error)| {
            Ok((
                optional_authored_value_to_python(py, value)?,
                offsets,
                error,
            ))
        })
        .collect()
}

#[pyfunction]
fn tokenize_model_header(header: &str) -> PyResult<Vec<(u8, String, usize)>> {
    crate::compiler::main::model_header_tokenizing::tokenize_one(header).map_err(value_error)
}

#[pyfunction]
fn substitute_static_project_vars(
    sqls: Vec<String>,
    variables: Vec<(String, String)>,
) -> Vec<(u8, Option<String>)> {
    crate::compiler::main::sql_interpolation::substitute_batch(&sqls, &variables)
}

#[pyfunction]
fn extract_static_sql_references(
    sql: &str,
) -> Option<Vec<crate::compiler::_helpers::sql_references::extraction::StaticReference>> {
    crate::compiler::main::sql_references::extract(sql)
}

#[pyfunction]
fn load_config_json(project_dir: &str) -> PyResult<String> {
    load::load_config_json(std::path::Path::new(project_dir)).map_err(value_error)
}

#[pyfunction]
fn catalogue_json() -> PyResult<String> {
    serde_json::to_string(&CatalogueResponse {
        version: API_VERSION,
        rules: catalogue::catalogue(),
    })
    .map_err(value_error)
}

#[pyfunction]
fn selected_codes_json(request_json: &str) -> PyResult<String> {
    selected_codes::selected_codes_json(request_json).map_err(value_error)
}

#[pyfunction]
fn render_owned_skill(content: &str, input_fingerprint: &str) -> PyResult<String> {
    fensu_policy::render_owned_skill(
        SKILL_OWNER,
        SKILL_IDENTITY,
        input_fingerprint,
        content.as_bytes(),
    )
    .map_err(value_error)
    .and_then(|value| String::from_utf8(value).map_err(value_error))
}

#[pyfunction]
fn skill_freshness(content: Option<&str>, input_fingerprint: &str) -> String {
    let freshness = fensu_policy::skill_freshness(
        content.map(str::as_bytes),
        SKILL_OWNER,
        SKILL_IDENTITY,
        input_fingerprint,
    );
    format!("{freshness:?}").to_lowercase()
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(evaluate_json, module)?)?;
    module.add_function(wrap_pyfunction!(finalize_rule_findings_json, module)?)?;
    module.add_function(wrap_pyfunction!(lint_sql_json, module)?)?;
    module.add_function(wrap_pyfunction!(prepare_lint_sql, module)?)?;
    module.add_function(wrap_pyfunction!(lint_backtick_identifiers, module)?)?;
    module.add_function(wrap_pyfunction!(lint_sql_batch_json, module)?)?;
    module.add_function(wrap_pyfunction!(format_sql_json, module)?)?;
    module.add_function(wrap_pyfunction!(format_sql_batch_json, module)?)?;
    module.add_function(wrap_pyfunction!(schema_validation_json, module)?)?;
    module.add_function(wrap_pyfunction!(schema_validations_json, module)?)?;
    module.add_function(wrap_pyfunction!(analyze_sql_uses_json, module)?)?;
    module.add_function(wrap_pyfunction!(analyze_queries_json, module)?)?;
    module.add_function(wrap_pyfunction!(analyze_project_queries_json, module)?)?;
    module.add_function(wrap_pyfunction!(
        analyze_project_queries_compact_json,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(render_sql_test_comparisons_json, module)?)?;
    module.add_function(wrap_pyfunction!(plan_and_render_sql_tests_json, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_sql_test_chains_json, module)?)?;
    module.add_function(wrap_pyfunction!(
        render_sql_test_difference_sample_json,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(extract_sql_tests_json, module)?)?;
    module.add_function(wrap_pyfunction!(parse_model_headers, module)?)?;
    module.add_function(wrap_pyfunction!(tokenize_model_header, module)?)?;
    module.add_function(wrap_pyfunction!(substitute_static_project_vars, module)?)?;
    module.add_function(wrap_pyfunction!(extract_static_sql_references, module)?)?;
    module.add_function(wrap_pyfunction!(load_config_json, module)?)?;
    module.add_function(wrap_pyfunction!(catalogue_json, module)?)?;
    module.add_function(wrap_pyfunction!(selected_codes_json, module)?)?;
    module.add_function(wrap_pyfunction!(render_owned_skill, module)?)?;
    module.add_function(wrap_pyfunction!(skill_freshness, module)?)?;
    module.add("API_VERSION", API_VERSION)?;
    Ok(())
}
