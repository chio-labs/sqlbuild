//! The Python host the loop hands finished models and user-code steps to.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{FromPyObject, IntoPyObject};
use sqlbuild_analysis::compiled_project::main::plain_model_facts::plain_model_facts;
use sqlbuild_analysis::compiled_project::models::{
    CompiledModelFacts, ModelConfigFacts, PlainModel,
};

use crate::bindings::_helpers::compiled_project::model_loop_header::{
    AttachedHeader, HeaderSchema,
};
use crate::bindings::_helpers::compiled_project::model_loop_inputs::{
    reference_fact, stripped_values,
};
use crate::bindings::_helpers::compiled_project::project::{
    DeclarationPy, ModelInputPy, config_values, declarations, model_facts,
};
use crate::bindings::_helpers::render::declaration_expansion::{
    ExpandedDeclarations, ScannedReference, span_rows,
};

const PLAIN_INPUT_CALLBACK: &str = "plain_input";
const FALLBACK_CALLBACK: &str = "fallback";
const MODEL_ROW_CALLBACK: &str = "model_row";
const HEADER_KEYS_ATTRIBUTE: &str = "model_header_keys";
const LAYER_SCHEMA_ATTRIBUTE: &str = "layer_schema";
const MODEL_INPUT_ARGUMENT: &str = "model_input";
const VALUES_ARGUMENT: &str = "values";
const REFERENCES_ARGUMENT: &str = "references";
const QUERY_SQL_ARGUMENT: &str = "query_sql";
const HEADER_ARGUMENT: &str = "header";
const HOOK_STATEMENTS_ARGUMENT: &str = "hook_statements";
const DECLARATIONS_ARGUMENT: &str = "declarations";
const ANALYSIS_ARGUMENT: &str = "analysis";

/// `((name, POSIX path, relative path, file path), column locations, query, contents, scan)`.
#[derive(FromPyObject)]
pub(crate) struct ModelLoopRow(
    pub(crate) (String, String, String, String),
    /// Header column locations, header values, and the model's own enums and constants.
    pub(crate) (Py<PyDict>, Py<PyDict>, Py<PyAny>, Py<PyAny>),
    pub(crate) String,
    pub(crate) String,
    pub(crate) Option<(Vec<ScannedReference>, Option<u8>)>,
    /// The `@@`-interpolated query, the template reads it made, or the error that stopped it.
    pub(crate) (String, Vec<(String, String)>, Option<String>),
);
/// `(kind, name, package, call argument count)`.
pub(crate) type ReferenceRow = (String, String, Option<String>, Option<usize>);
/// The Python view of the model and its visible local enum and constant declarations.
type PlainInputPy<'py> = (
    Bound<'py, PyAny>,
    (Vec<DeclarationPy<'py>>, Vec<DeclarationPy<'py>>),
);

/// One model the native loop finished, before the host builds its Python view.
pub(crate) struct FinishedModel<'py> {
    pub(crate) config: Bound<'py, PyAny>,
    /// The hook-expanded config values, header metadata still included.
    pub(crate) values: Bound<'py, PyDict>,
    pub(crate) query_sql: String,
    pub(crate) header: AttachedHeader<'py>,
    pub(crate) references: Vec<ReferenceRow>,
    pub(crate) declarations: ExpandedDeclarations<'py>,
    pub(crate) hook_statements: usize,
    /// Whether the SQL is analysed, and where a rejected `sql_analysis false` was authored.
    pub(crate) analysis: (bool, Option<Bound<'py, PyAny>>),
    /// The usages of the model's named schema and Python hooks, recorded after its hook usages.
    pub(crate) named_usages: Vec<Bound<'py, PyAny>>,
}

/// Call a host callback with keyword arguments, as its keyword-only signature requires.
pub(crate) fn callback<'py>(
    host: &Bound<'py, PyAny>,
    name: &str,
    arguments: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    let keywords: Bound<'py, PyDict> = PyDict::new(host.py());
    for (key, value) in arguments {
        keywords.set_item(*key, value)?;
    }
    host.call_method(name, (), Some(&keywords))
}

/// The host's Python view of a natively finished model, and the facts the project retains.
pub(crate) fn plain_input<'py>(
    host: &Bound<'py, PyAny>,
    model_arguments: &[(&str, Bound<'py, PyAny>)],
    row: ModelLoopRow,
    finished: FinishedModel<'py>,
) -> PyResult<(Bound<'py, PyAny>, CompiledModelFacts)> {
    let py: Python<'py> = host.py();
    let ModelLoopRow((name, relative_path, _, _), _, authored_query_sql, authored_sql, _, _) = row;
    let stripped: Bound<'py, PyDict> = stripped_values(py, &finished.values)?;
    let mut usages: Vec<Bound<'py, PyAny>> = finished.declarations.usages;
    if let Some(schema) = &finished.header.schema {
        usages.extend(schema.generated_usages.iter().cloned());
    }
    let enum_columns: Vec<String> = match &finished.header.schema {
        Some(schema) => schema.enum_columns.keys().extract()?,
        None => Vec::new(),
    };
    let mut arguments: Vec<(&str, Bound<'py, PyAny>)> = model_arguments.to_vec();
    arguments.extend([
        (VALUES_ARGUMENT, stripped.clone().into_any()),
        (
            REFERENCES_ARGUMENT,
            finished.references.clone().into_pyobject(py)?,
        ),
        (
            QUERY_SQL_ARGUMENT,
            finished.query_sql.as_str().into_pyobject(py)?.into_any(),
        ),
        (
            HEADER_ARGUMENT,
            PyTuple::new(
                py,
                [
                    finished.header.description.as_deref().into_pyobject(py)?,
                    schema_argument(py, finished.header.schema.as_ref())?,
                    finished.header.schema.as_ref().map_or_else(
                        || PyDict::new(py).into_any(),
                        |schema| schema.enum_columns.clone().into_any(),
                    ),
                ],
            )?
            .into_any(),
        ),
        (
            ANALYSIS_ARGUMENT,
            finished.analysis.clone().into_pyobject(py)?.into_any(),
        ),
        (
            HOOK_STATEMENTS_ARGUMENT,
            finished.hook_statements.into_pyobject(py)?.into_any(),
        ),
        (
            DECLARATIONS_ARGUMENT,
            (
                finished.declarations.spliced.sql.as_str(),
                span_rows(&finished.declarations.spliced),
                usages,
                finished.named_usages,
            )
                .into_pyobject(py)?
                .into_any(),
        ),
    ]);
    let (input, (enums, constants)): PlainInputPy<'py> =
        callback(host, PLAIN_INPUT_CALLBACK, &arguments)?.extract()?;
    let (values, encoding_error) = config_values(&stripped);
    let facts: CompiledModelFacts = plain_model_facts(PlainModel {
        name,
        relative_path,
        query_sql: finished.query_sql,
        authored_query_sql,
        authored_sql,
        config: ModelConfigFacts {
            values,
            encoding_error,
            header_keys: finished.config.getattr(HEADER_KEYS_ATTRIBUTE)?.extract()?,
            layer_schema: finished.config.getattr(LAYER_SCHEMA_ATTRIBUTE)?.extract()?,
        },
        schema: finished.header.schema.map(|schema| schema.fact),
        references: finished
            .references
            .into_iter()
            .map(reference_fact)
            .collect(),
        enum_columns,
        enum_declarations: declarations(enums)?,
        constant_declarations: declarations(constants)?,
    });
    Ok((input, facts))
}

/// The attachment's model input, after all its callbacks ran, and the facts read from it.
pub(crate) fn attached_input<'py>(
    host: &Bound<'py, PyAny>,
    model_arguments: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<(Bound<'py, PyAny>, CompiledModelFacts)> {
    let input: Bound<'py, PyAny> = callback(host, FALLBACK_CALLBACK, model_arguments)?;
    let row: ModelInputPy<'_> = callback(
        host,
        MODEL_ROW_CALLBACK,
        &[(MODEL_INPUT_ARGUMENT, input.clone())],
    )?
    .extract()?;
    Ok((input, model_facts(row)?))
}

/// The schema argument the host builds its `SchemaModelEntry` from.
fn schema_argument<'py>(
    py: Python<'py>,
    schema: Option<&HeaderSchema<'py>>,
) -> PyResult<Bound<'py, PyAny>> {
    match schema {
        Some(schema) => Ok((
            schema.columns.clone(),
            schema.audits.clone(),
            schema.type_enforcement,
            schema.dynamic_columns.clone(),
            schema.model_schema.clone(),
        )
            .into_pyobject(py)?
            .into_any()),
        None => Ok(py.None().into_bound(py)),
    }
}
