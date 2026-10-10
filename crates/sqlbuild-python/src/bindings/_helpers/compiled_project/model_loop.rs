//! The compile-input model loop: models it can finish natively go straight into the owned project.

use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyRefMut, PyResult, Python,
};
use pyo3::types::{PyBool, PyBoolMethods, PyDict, PyDictMethods, PyString, PyStringMethods};
use pyo3::{IntoPyObject, pyclass, pymethods};
use sqlbuild_analysis::compiled_project::main::header_metadata_keys::is_header_metadata_key;
use sqlbuild_analysis::compiled_project::main::plain_model_blocker::plain_model_blocker;
use sqlbuild_analysis::compiled_project::main::plain_model_facts::plain_model_facts;
use sqlbuild_analysis::compiled_project::models::{
    AnalysisOverride, CompiledModelFacts, DescriptionShape, ModelConfigFacts, ModelLoopSettings,
    ModelReferenceFact, PlainModel, PlainModelCheck,
};
use sqlbuild_attachments::cursor_intrinsics::main::validated_model_intrinsics::validated_model_intrinsics;
use sqlbuild_attachments::cursor_intrinsics::models::IntrinsicModel;
use sqlbuild_core::text::models::PythonText;
use sqlbuild_sqltext::sql_references::main::extract_sql_references::extract_sql_references;
use sqlbuild_sqltext::sql_references::models::{ReferenceExtraction, SqlReference};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::bindings::_helpers::compiled_project::project::{
    DeclarationPy, ModelInputPy, NativeCompiledProject, config_values, declarations, model_facts,
};
use crate::bindings::_helpers::discovery::project_files::python_semantics;
use crate::bindings::_helpers::sqltext::lexical_syntax::LexicalSyntaxInput;

const DESCRIPTION_KEY: &str = "description";
const SQL_ANALYSIS_KEY: &str = "sql_analysis";
const SQL_VALIDATION_KEY: &str = "sql_validation";
const MATERIALIZED_KEY: &str = "materialized";
const CURSOR_KEY: &str = "cursor";
const INCREMENTAL_MATERIALIZATION: &str = "incremental";
const DBT_REF_KIND: &str = "dbt_ref";
const VALUES_ATTRIBUTE: &str = "values";
const HEADER_KEYS_ATTRIBUTE: &str = "model_header_keys";
const LAYER_SCHEMA_ATTRIBUTE: &str = "layer_schema";
const RETENTION_ATTRIBUTE: &str = "time_travel_retention";
const UNMANAGED_ATTRIBUTE: &str = "unmanaged";
const TABLE_TYPE_ATTRIBUTE: &str = "table_type";
const DECLARED_ATTRIBUTE: &str = "declared";
const STRIP_METHOD: &str = "strip";
const VALIDATE_METHOD: &str = "validate";
const CONFIG_CALLBACK: &str = "config";
const PLAIN_INPUT_CALLBACK: &str = "plain_input";
const FALLBACK_CALLBACK: &str = "fallback";
const MODEL_ROW_CALLBACK: &str = "model_row";
const INDEX_ARGUMENT: &str = "index";
const MODEL_INPUT_ARGUMENT: &str = "model_input";
const VALUES_ARGUMENT: &str = "values";
const REFERENCES_ARGUMENT: &str = "references";
const QUERY_SQL_ARGUMENT: &str = "query_sql";
const DESCRIPTION_ARGUMENT: &str = "description";

/// Identity paths, authored query, contents, interpolated query and declaration references.
type ModelLoopRow = (
    (String, String, String),
    String,
    String,
    Option<String>,
    bool,
);
/// `(kind, name, package, call argument count)`.
type ReferenceRow = (String, String, Option<String>, Option<usize>);
/// The Python view of the model and its visible local enum and constant declarations.
type PlainInputPy<'py> = (
    Bound<'py, PyAny>,
    (Vec<DeclarationPy<'py>>, Vec<DeclarationPy<'py>>),
);

/// The ordered model loop of one compile-input stage.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeModelLoop {
    validator: Py<PyAny>,
    syntax: LexicalSyntax,
    reserved_markers: Vec<String>,
    python: PythonText,
    settings: ModelLoopSettings,
}

/// What the native validator reads for one model.
struct Validation<'a, 'py> {
    config: &'a Bound<'py, PyAny>,
    values: &'a Bound<'py, PyDict>,
    model: (&'a str, &'a str, &'a str),
    references: &'a [SqlReference],
}

/// One model the native loop finished, before the host builds its Python view.
struct FinishedModel<'py> {
    config: Bound<'py, PyAny>,
    stripped: Bound<'py, PyDict>,
    query_sql: String,
    description: Option<String>,
    references: Vec<SqlReference>,
}

#[pymethods]
impl NativeModelLoop {
    #[new]
    fn new(
        validator: Py<PyAny>,
        syntax: LexicalSyntaxInput,
        cursor: (Vec<String>, ((u8, u8), String)),
        settings: (bool, bool, bool, bool),
    ) -> PyResult<Self> {
        let (reserved_markers, (python_version, unicode_version)) = cursor;
        let (sql_analysis, no_sql_validation, defer_sql_validation, legacy_schema_files) = settings;
        Ok(Self {
            validator,
            syntax: syntax.into(),
            reserved_markers,
            python: python_semantics(python_version, &unicode_version)?,
            settings: ModelLoopSettings {
                sql_analysis,
                no_sql_validation,
                defer_sql_validation,
                legacy_schema_files,
            },
        })
    }

    /// Build every model in order into `project`; return the Python views and the native count.
    fn run<'py>(
        &self,
        py: Python<'py>,
        mut project: PyRefMut<'py, NativeCompiledProject>,
        host: Bound<'py, PyAny>,
        models: Vec<ModelLoopRow>,
    ) -> PyResult<(Vec<Bound<'py, PyAny>>, usize)> {
        let mut inputs: Vec<Bound<'py, PyAny>> = Vec::with_capacity(models.len());
        let mut finished_natively: usize = 0;
        for (index, row) in models.into_iter().enumerate() {
            let index_argument = [(INDEX_ARGUMENT, index.into_pyobject(py)?.into_any())];
            let config: Bound<'py, PyAny> = callback(&host, CONFIG_CALLBACK, &index_argument)?;
            let (input, facts) = match self.finish(py, &row, config)? {
                Some(finished) => {
                    finished_natively += 1;
                    plain_input(&host, index, row, finished)?
                }
                None => attached_input(&host, &index_argument)?,
            };
            project.retain(facts);
            inputs.push(input);
        }
        Ok((inputs, finished_natively))
    }
}

impl NativeModelLoop {
    /// The model finished natively, or `None` when the Python attachment must finish it.
    fn finish<'py>(
        &self,
        py: Python<'py>,
        row: &ModelLoopRow,
        config: Bound<'py, PyAny>,
    ) -> PyResult<Option<FinishedModel<'py>>> {
        let ((name, _, relative_path), _, _, interpolated_sql, has_declaration_references) = row;
        let values: Bound<'py, PyDict> = config.getattr(VALUES_ATTRIBUTE)?.downcast_into()?;
        let check: PlainModelCheck = PlainModelCheck {
            config_keys: config_keys(&values)?,
            description: description_shape(&values)?,
            analysis_override: analysis_override(&values)?,
            interpolated_sql: interpolated_sql.clone(),
            has_declaration_references: *has_declaration_references,
            settings: self.settings,
        };
        let (None, Some(sql)) = (plain_model_blocker(&check), interpolated_sql) else {
            return Ok(None);
        };
        let Ok(query_sql) = self.canonical_query(name, sql, &values)? else {
            return Ok(None);
        };
        let ReferenceExtraction::Extracted(scan) = extract_sql_references(&query_sql, &self.syntax)
        else {
            return Ok(None);
        };
        if !scan.invalid_calls.is_empty()
            || scan
                .references
                .iter()
                .any(|reference| reference.kind == DBT_REF_KIND)
        {
            return Ok(None);
        }
        let validation: Validation<'_, 'py> = Validation {
            config: &config,
            values: &values,
            model: (name, &query_sql, relative_path),
            references: &scan.references,
        };
        if !self.validates(py, &validation)? {
            return Ok(None);
        }
        let description: Option<String> = match check.description {
            DescriptionShape::Text(description) => Some(description),
            DescriptionShape::Absent | DescriptionShape::Invalid => None,
        };
        Ok(Some(FinishedModel {
            stripped: stripped_values(py, &values)?,
            config,
            query_sql,
            description,
            references: scan.references,
        }))
    }

    /// The query with canonical cursor intrinsics, or the message the attachment raises.
    fn canonical_query(
        &self,
        name: &str,
        sql: &str,
        values: &Bound<'_, PyDict>,
    ) -> PyResult<Result<String, String>> {
        let incremental: bool = values
            .get_item(MATERIALIZED_KEY)?
            .is_some_and(|value| is_text(&value, INCREMENTAL_MATERIALIZATION));
        let cursor: Option<String> = match values.get_item(CURSOR_KEY)? {
            Some(value) => match value.downcast::<PyString>() {
                Ok(text) => Some(text.to_string_lossy().into_owned()),
                Err(_) => None,
            },
            None => None,
        };
        let model: IntrinsicModel<'_> = IntrinsicModel {
            name,
            incremental,
            cursor: cursor.as_deref(),
        };
        Ok(validated_model_intrinsics(
            self.python,
            sql,
            &self.reserved_markers,
            &model,
        ))
    }

    /// Whether the native validator accepts the model; a rejection is reported by Python.
    fn validates(&self, py: Python<'_>, validation: &Validation<'_, '_>) -> PyResult<bool> {
        let rows: Vec<(&str, &str, bool)> = validation
            .references
            .iter()
            .map(|reference| (reference.kind, reference.name.as_str(), false))
            .collect();
        let unmanaged: Bound<'_, PyAny> = validation
            .config
            .getattr(RETENTION_ATTRIBUTE)?
            .getattr(UNMANAGED_ATTRIBUTE)?;
        let declared: Bound<'_, PyAny> = validation
            .config
            .getattr(TABLE_TYPE_ATTRIBUTE)?
            .getattr(DECLARED_ATTRIBUTE)?;
        let outcome: Bound<'_, PyAny> = self.validator.bind(py).call_method1(
            VALIDATE_METHOD,
            (
                validation.values.clone(),
                validation.model,
                (rows, py.None(), unmanaged, declared),
            ),
        )?;
        Ok(outcome.is_none())
    }
}

/// The host's Python view of a natively finished model, and the facts the project retains.
fn plain_input<'py>(
    host: &Bound<'py, PyAny>,
    index: usize,
    row: ModelLoopRow,
    finished: FinishedModel<'py>,
) -> PyResult<(Bound<'py, PyAny>, CompiledModelFacts)> {
    let py: Python<'py> = host.py();
    let ((name, relative_path, _), authored_query_sql, authored_sql, _, _) = row;
    let reference_rows: Vec<ReferenceRow> = finished.references.iter().map(reference_row).collect();
    let arguments = [
        (INDEX_ARGUMENT, index.into_pyobject(py)?.into_any()),
        (VALUES_ARGUMENT, finished.stripped.clone().into_any()),
        (REFERENCES_ARGUMENT, reference_rows.into_pyobject(py)?),
        (
            QUERY_SQL_ARGUMENT,
            finished.query_sql.as_str().into_pyobject(py)?.into_any(),
        ),
        (
            DESCRIPTION_ARGUMENT,
            finished.description.as_deref().into_pyobject(py)?,
        ),
    ];
    let (input, (enums, constants)): PlainInputPy<'py> =
        callback(host, PLAIN_INPUT_CALLBACK, &arguments)?.extract()?;
    let (values, encoding_error) = config_values(&finished.stripped);
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
        description: finished.description,
        references: finished
            .references
            .into_iter()
            .map(reference_fact)
            .collect(),
        enum_declarations: declarations(enums)?,
        constant_declarations: declarations(constants)?,
    });
    Ok((input, facts))
}

/// The attachment's model input, after all its callbacks ran, and the facts read from it.
fn attached_input<'py>(
    host: &Bound<'py, PyAny>,
    index_argument: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<(Bound<'py, PyAny>, CompiledModelFacts)> {
    let input: Bound<'py, PyAny> = callback(host, FALLBACK_CALLBACK, index_argument)?;
    let row: ModelInputPy<'_> = callback(
        host,
        MODEL_ROW_CALLBACK,
        &[(MODEL_INPUT_ARGUMENT, input.clone())],
    )?
    .extract()?;
    Ok((input, model_facts(row)?))
}

/// Call a host callback with keyword arguments, as its keyword-only signature requires.
fn callback<'py>(
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

fn reference_row(reference: &SqlReference) -> ReferenceRow {
    (
        reference.kind.to_owned(),
        reference.name.clone(),
        reference.package.clone(),
        reference.call_argument_count,
    )
}

fn reference_fact(reference: SqlReference) -> ModelReferenceFact {
    ModelReferenceFact {
        kind: reference.kind.to_owned(),
        name: reference.name,
        package: reference.package,
    }
}

fn config_keys(values: &Bound<'_, PyDict>) -> PyResult<Vec<String>> {
    let mut keys: Vec<String> = Vec::with_capacity(values.len());
    for key in values.keys() {
        keys.push(key.str()?.to_string());
    }
    Ok(keys)
}

/// The config without header metadata, always a new dictionary as hook expansion leaves it.
fn stripped_values<'py>(
    py: Python<'py>,
    values: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    let stripped: Bound<'py, PyDict> = PyDict::new(py);
    for (key, value) in values.iter() {
        if !is_header_metadata_key(&key.str()?.to_string()) {
            stripped.set_item(key, value)?;
        }
    }
    Ok(stripped)
}

/// Absent, a non-blank string by Python's `str.strip`, or anything the attachment rejects.
fn description_shape(values: &Bound<'_, PyDict>) -> PyResult<DescriptionShape> {
    let Some(value) = values.get_item(DESCRIPTION_KEY)? else {
        return Ok(DescriptionShape::Absent);
    };
    if value.is_none() {
        return Ok(DescriptionShape::Absent);
    }
    let Ok(text) = value.downcast::<PyString>() else {
        return Ok(DescriptionShape::Invalid);
    };
    if text.call_method0(STRIP_METHOD)?.is_truthy()? {
        Ok(DescriptionShape::Text(text.to_str()?.to_owned()))
    } else {
        Ok(DescriptionShape::Invalid)
    }
}

fn analysis_override(values: &Bound<'_, PyDict>) -> PyResult<AnalysisOverride> {
    let analysis: Option<Bound<'_, PyAny>> = present(values, SQL_ANALYSIS_KEY)?;
    let legacy: Option<Bound<'_, PyAny>> = present(values, SQL_VALIDATION_KEY)?;
    Ok(match (analysis, legacy) {
        (Some(_), Some(_)) => AnalysisOverride::Ambiguous,
        (Some(value), None) | (None, Some(value)) => match value.downcast::<PyBool>() {
            Ok(flag) if flag.is_true() => AnalysisOverride::Enabled,
            Ok(_) => AnalysisOverride::Disabled,
            Err(_) => AnalysisOverride::Inherit,
        },
        (None, None) => AnalysisOverride::Inherit,
    })
}

/// The value under `key`, treating an explicit `None` as absent.
fn present<'py>(values: &Bound<'py, PyDict>, key: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
    Ok(values.get_item(key)?.filter(|value| !value.is_none()))
}

fn is_text(value: &Bound<'_, PyAny>, expected: &str) -> bool {
    value
        .downcast::<PyString>()
        .is_ok_and(|text| text.to_string_lossy() == expected)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeModelLoop>()
}
