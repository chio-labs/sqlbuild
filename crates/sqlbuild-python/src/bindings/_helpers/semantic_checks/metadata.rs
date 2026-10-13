//! Native semantic metadata checks: config references, cursors, function calls and SQL tests.

use std::sync::Arc;

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyFloat, PyInt, PyList, PyString, PyTuple};
use sqlbuild_analysis::semantic_checks::main::check_semantic_metadata::check_semantic_metadata;
use sqlbuild_analysis::semantic_checks::models::{
    AuditValue, MetadataAudit, MetadataFinding, MetadataFunction, MetadataModel, MetadataRequest,
    MetadataSource, MetadataSqlTest, ModelMetadataFindings,
};
use sqlbuild_analysis::semantic_validation::models as validation;

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::semantic_checks::failures::semantic_error;
use crate::bindings::_helpers::semantic_checks::inputs::{
    column_names, resource_sql_diagnostics, sql_test_columns,
};
use crate::bindings::_helpers::semantic_checks::stage_objects::StageClasses;
use crate::bindings::_helpers::semantic_checks::type_recovery::items;
use crate::bindings::_helpers::semantic_shapes::shapes::project_shapes;
use crate::bindings::types::CompilerDetach;

const METADATA_CONFIG_KEYS: [&str; 4] = [
    "unique_key",
    "cursor",
    "partition_column",
    "row_diff_exclude_columns",
];

/// `[(relation, [(column, value)])]` in Python's order.
pub(crate) type ShapeRows = Vec<(String, Vec<(String, String)>)>;
/// `(key, names)` pairs in Python's order.
type NamesRow = (String, Vec<String>);

/// The relations the metadata request reads, kept for building its diagnostics.
struct MetadataInputs<'py> {
    shapes: Bound<'py, PyAny>,
    models: Vec<Bound<'py, PyAny>>,
    sources: Vec<Bound<'py, PyAny>>,
    tests: Vec<Bound<'py, PyAny>>,
}

/// The project's semantic metadata diagnostics, then its resource SQL diagnostics when asked.
pub(crate) fn metadata_diagnostics<'py>(
    classes: &StageClasses<'py>,
    (project, profile): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    resource_sql_analysis: bool,
    catalog: &validation::ProjectCatalog,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py: Python<'py> = classes.py();
    if !project
        .getattr("settings")?
        .getattr("sql_analysis")?
        .is_truthy()?
    {
        return Ok(Vec::new());
    }
    let (inputs, request) = metadata_request(classes, project, profile)?;
    let outcome = py
        .compiler_detach(|| Ok(check_semantic_metadata(&request, catalog)))
        .map_err(compiler_error)?
        .map_err(|failure| semantic_error(py, &failure))?;
    let dialect: Bound<'py, PyAny> = profile.getattr("sql_analysis_dialect")?;
    for type_sql in &outcome.fallback_types {
        let _ = classes.call(
            &classes.normalize_type,
            &[
                ("type_sql", &PyString::new(py, type_sql).into_any()),
                ("dialect", &dialect),
            ],
        )?;
    }
    let mut diagnostics: Vec<Bound<'py, PyAny>> = Vec::new();
    for (model, findings) in inputs.models.iter().zip(outcome.models) {
        if checked(classes, model)? {
            diagnostics.extend(model_diagnostics(classes, model, findings)?);
        }
    }
    for (index, finding) in outcome.sources {
        let source: &Bound<'py, PyAny> = &inputs.sources[index];
        let path: Bound<'py, PyAny> = source.getattr("source_file")?.getattr("relative_path")?;
        diagnostics.push(diagnostic(
            classes,
            finding,
            (&classes.source_resource, &source.getattr("name")?),
            (&path, None),
        )?);
    }
    for (index, finding, end_column) in outcome.sql_tests {
        diagnostics.push(sql_test_diagnostic(
            classes,
            &inputs.tests[index],
            finding,
            end_column,
        )?);
    }
    if resource_sql_analysis {
        let resource: Bound<'py, PyAny> =
            resource_sql_diagnostics(project, &inputs.shapes, profile)?;
        diagnostics.extend(items(&resource)?);
    }
    Ok(diagnostics)
}

fn metadata_request<'py>(
    classes: &StageClasses<'py>,
    project: &Bound<'py, PyAny>,
    profile: &Bound<'py, PyAny>,
) -> PyResult<(MetadataInputs<'py>, MetadataRequest)> {
    let shapes: Bound<'py, PyAny> = project_shapes(project, Some(profile.clone()))?.into_any();
    let mut tests: Vec<Bound<'py, PyAny>> = Vec::new();
    for test in project.getattr("sql_tests")?.try_iter()? {
        let test: Bound<'py, PyAny> = test?;
        if test
            .getattr("payload")?
            .is_instance(&classes.model_test_payload)?
        {
            tests.push(test);
        }
    }
    let columns_by_sql: Bound<'py, PyAny> =
        sql_test_columns(project, profile, &classes.model_test_payload)?.into_any();
    let functions: Vec<MetadataFunction> = metadata_functions(project)?;
    let sources: Vec<Bound<'py, PyAny>> = items(&project.getattr("sources")?)?;
    let (files, contents) = file_contents(classes.py(), &sources, &tests)?;
    let models: Vec<Bound<'py, PyAny>> = items(&project.getattr("models")?)?;
    let mut metadata_models: Vec<MetadataModel> = Vec::with_capacity(models.len());
    for model in &models {
        metadata_models.push(metadata_model(classes, model)?);
    }
    let mut metadata_sources: Vec<MetadataSource> = Vec::with_capacity(sources.len());
    for source in &sources {
        let cursor: Bound<'py, PyAny> = source.getattr("source_entry")?.getattr("cursor_column")?;
        let index: usize = file_index(&files, &source.getattr("source_file")?)?;
        metadata_sources.push(MetadataSource {
            name: source.getattr("name")?.extract()?,
            cursor_column: if cursor.is_truthy()? {
                Some(cursor.extract()?)
            } else {
                None
            },
            contents: contents[index].clone(),
        });
    }
    let mut metadata_tests: Vec<MetadataSqlTest> = Vec::with_capacity(tests.len());
    for test in &tests {
        let index: usize = file_index(&files, &test.getattr("test_file")?)?;
        metadata_tests.push(MetadataSqlTest {
            contents: contents[index].clone(),
            ctes: test_ctes(&test.getattr("payload")?, &columns_by_sql)?,
        });
    }
    let request = MetadataRequest {
        dialect: profile.getattr("sql_analysis_dialect")?.extract()?,
        quoted_ignore_case: profile
            .getattr("quoted_identifiers_ignore_case")?
            .extract()?,
        return_types: pairs(&profile.getattr("function_return_types")?)?,
        functions,
        shapes: shape_rows(&shapes)?,
        models: metadata_models,
        sources: metadata_sources,
        sql_tests: metadata_tests,
    };
    let inputs = MetadataInputs {
        shapes,
        models,
        sources,
        tests,
    };
    Ok((inputs, request))
}

/// Declared functions by `name.casefold()`, the last declaration winning in the first's place.
fn metadata_functions(project: &Bound<'_, PyAny>) -> PyResult<Vec<MetadataFunction>> {
    let functions: Bound<'_, PyDict> = PyDict::new(project.py());
    for function in project.getattr("functions")?.try_iter()? {
        let function: Bound<'_, PyAny> = function?;
        functions.set_item(
            function.getattr("name")?.call_method0("casefold")?,
            &function,
        )?;
    }
    let mut metadata: Vec<MetadataFunction> = Vec::with_capacity(functions.len());
    for (key, function) in functions.iter() {
        let mut arguments: Vec<(String, String)> = Vec::new();
        for argument in function.getattr("arguments")?.try_iter()? {
            let argument: Bound<'_, PyAny> = argument?;
            arguments.push((
                argument.getattr("name")?.extract()?,
                argument.getattr("type")?.extract()?,
            ));
        }
        metadata.push(MetadataFunction {
            key: key.extract()?,
            arguments,
        });
    }
    Ok(metadata)
}

/// Each distinct file path's index and the text its first resource carries.
fn file_contents<'py>(
    py: Python<'py>,
    sources: &[Bound<'py, PyAny>],
    tests: &[Bound<'py, PyAny>],
) -> PyResult<(Bound<'py, PyDict>, Vec<Arc<str>>)> {
    let file_texts: Bound<'py, PyDict> = PyDict::new(py);
    for file in sources
        .iter()
        .map(|source| source.getattr("source_file"))
        .chain(tests.iter().map(|test| test.getattr("test_file")))
    {
        let file: Bound<'py, PyAny> = file?;
        let path: Bound<'py, PyAny> = file.getattr("file_path")?;
        if !file_texts.contains(&path)? {
            file_texts.set_item(path, file.getattr("contents")?)?;
        }
    }
    let files: Bound<'py, PyDict> = PyDict::new(py);
    let mut contents: Vec<Arc<str>> = Vec::with_capacity(file_texts.len());
    for (index, (path, text)) in file_texts.iter().enumerate() {
        files.set_item(path, index)?;
        contents.push(Arc::from(text.extract::<String>()?));
    }
    Ok((files, contents))
}

fn file_index(files: &Bound<'_, PyDict>, file: &Bound<'_, PyAny>) -> PyResult<usize> {
    files
        .as_any()
        .get_item(file.getattr("file_path")?)?
        .extract()
}

/// Each authored and expected CTE's name with the columns its body infers.
fn test_ctes(
    payload: &Bound<'_, PyAny>,
    columns_by_sql: &Bound<'_, PyAny>,
) -> PyResult<Vec<NamesRow>> {
    let mut ctes: Vec<NamesRow> = Vec::new();
    for cte in payload
        .getattr("authored_ctes")?
        .try_iter()?
        .chain(payload.getattr("expected_ctes")?.try_iter()?)
    {
        let cte: Bound<'_, PyAny> = cte?;
        ctes.push((
            cte.getattr("name")?.extract()?,
            columns_by_sql
                .get_item(cte.getattr("sql_body")?)?
                .try_iter()?
                .map(|name| name?.extract())
                .collect::<PyResult<_>>()?,
        ));
    }
    Ok(ctes)
}

/// A checked model's function errors, then its audit findings, then its reference errors.
fn model_diagnostics<'py>(
    classes: &StageClasses<'py>,
    model: &Bound<'py, PyAny>,
    findings: ModelMetadataFindings,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut diagnostics: Vec<Bound<'py, PyAny>> = Vec::new();
    for finding in findings.functions {
        diagnostics.push(model_error(
            classes,
            model,
            &finding_row(&finding),
            &classes.error,
        )?);
    }
    for audit in findings.audits {
        let severity: &Bound<'py, PyAny> = if audit.is_error {
            &classes.error
        } else {
            &classes.warning
        };
        let row: FindingRow<'_> = (&audit.code, &audit.message, audit.line, audit.column);
        diagnostics.push(model_error(classes, model, &row, severity)?);
    }
    for finding in findings.references {
        diagnostics.push(model_error(
            classes,
            model,
            &finding_row(&finding),
            &classes.error,
        )?);
    }
    Ok(diagnostics)
}

fn sql_test_diagnostic<'py>(
    classes: &StageClasses<'py>,
    test: &Bound<'py, PyAny>,
    finding: MetadataFinding,
    end_column: i64,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = classes.py();
    let path: Bound<'py, PyAny> = test.getattr("test_file")?.getattr("relative_path")?;
    let location: Bound<'py, PyAny> = classes.call(
        &classes.location,
        &[
            ("path", &path),
            ("line", &finding.line.into_bound_py_any(py)?),
            ("column", &finding.column.into_bound_py_any(py)?),
            ("end_line", &finding.line.into_bound_py_any(py)?),
            ("end_column", &end_column.into_bound_py_any(py)?),
        ],
    )?;
    diagnostic(
        classes,
        finding,
        (&classes.sql_test_resource, &test.getattr("name")?),
        (&path, Some(&location)),
    )
}

/// `{name: {column: value}}` as ordered rows.
pub(crate) fn shape_rows(shapes: &Bound<'_, PyAny>) -> PyResult<ShapeRows> {
    let mut rows: ShapeRows = Vec::new();
    for item in shapes.call_method0("items")?.try_iter()? {
        let (name, columns): (String, Bound<'_, PyAny>) = item?.extract()?;
        rows.push((name, pairs(&columns)?));
    }
    Ok(rows)
}

/// A `{key: value}` text mapping's items in order.
fn pairs(mapping: &Bound<'_, PyAny>) -> PyResult<Vec<(String, String)>> {
    mapping
        .call_method0("items")?
        .try_iter()?
        .map(|item| item?.extract())
        .collect()
}

/// `(code, message, line, column)`.
type FindingRow<'a> = (&'a str, &'a str, i64, i64);

fn finding_row(finding: &MetadataFinding) -> FindingRow<'_> {
    (finding.code, &finding.message, finding.line, finding.column)
}

fn model_error<'py>(
    classes: &StageClasses<'py>,
    model: &Bound<'py, PyAny>,
    &(code, message, line, column): &FindingRow<'_>,
    severity: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = classes.py();
    classes.call(
        &classes.diagnostic,
        &[
            ("phase", &classes.compile_phase),
            ("severity", severity),
            ("code", &PyString::new(py, code).into_any()),
            ("message", &PyString::new(py, message).into_any()),
            ("resource_type", &classes.model_resource),
            ("resource_name", &model.getattr("name")?),
            ("path", &model.getattr("relative_path")?),
            ("line", &line.into_bound_py_any(py)?),
            ("column", &column.into_bound_py_any(py)?),
        ],
    )
}

fn diagnostic<'py>(
    classes: &StageClasses<'py>,
    finding: MetadataFinding,
    (resource_type, resource_name): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (path, location): (&Bound<'py, PyAny>, Option<&Bound<'py, PyAny>>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = classes.py();
    let code: Bound<'py, PyAny> = PyString::new(py, finding.code).into_any();
    let message: Bound<'py, PyAny> = PyString::new(py, &finding.message).into_any();
    let line: Bound<'py, PyAny> = finding.line.into_bound_py_any(py)?;
    let column: Bound<'py, PyAny> = finding.column.into_bound_py_any(py)?;
    let mut arguments: Vec<(&str, &Bound<'py, PyAny>)> = vec![
        ("phase", &classes.compile_phase),
        ("severity", &classes.error),
        ("code", &code),
        ("message", &message),
        ("resource_type", resource_type),
        ("resource_name", resource_name),
        ("path", path),
        ("line", &line),
        ("column", &column),
    ];
    if let Some(location) = location {
        arguments.push(("location", location));
    }
    classes.call(&classes.diagnostic, &arguments)
}

/// Python's `config.get(sql_analysis) is not False and model.binding_validated`.
fn checked(classes: &StageClasses<'_>, model: &Bound<'_, PyAny>) -> PyResult<bool> {
    let opted: Bound<'_, PyAny> = model
        .getattr("config")?
        .getattr("values")?
        .call_method1("get", (&classes.sql_analysis_key,))?;
    if opted.is(PyBool::new(model.py(), false)) {
        return Ok(false);
    }
    model.getattr("binding_validated")?.is_truthy()
}

fn text(value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_instance_of::<PyString>() {
        return Ok(Some(value.extract()?));
    }
    Ok(None)
}

fn metadata_model(classes: &StageClasses<'_>, model: &Bound<'_, PyAny>) -> PyResult<MetadataModel> {
    let values: Bound<'_, PyAny> = model.getattr("config")?.getattr("values")?;
    let get = |key: &str| values.call_method1("get", (key,));
    let mut references: Vec<NamesRow> = Vec::new();
    for key in METADATA_CONFIG_KEYS {
        references.push((key.to_owned(), column_names(&get(key)?)?));
    }
    let custom: Bound<'_, PyAny> = get("config")?;
    if custom.is_instance_of::<PyDict>() {
        let partition: Bound<'_, PyAny> = custom.call_method1("get", ("partition_column",))?;
        references.push(("partition_column".to_owned(), column_names(&partition)?));
    }
    let tolerances: Bound<'_, PyAny> = get("row_diff_tolerances")?;
    if tolerances.is_instance_of::<PyDict>() {
        let by_column: Bound<'_, PyAny> = tolerances.call_method1("get", ("by_column",))?;
        if by_column.is_instance_of::<PyDict>() {
            let names: Vec<String> = by_column
                .try_iter()?
                .map(|name| name?.str()?.extract())
                .collect::<PyResult<_>>()?;
            references.push(("row_diff_tolerances".to_owned(), names));
        }
    }
    let cursor_inputs: Bound<'_, PyAny> = get("cursor_inputs")?;
    let mut upstreams: Vec<NamesRow> = Vec::new();
    if cursor_inputs.is_instance_of::<PyDict>() {
        for item in cursor_inputs.call_method0("items")?.try_iter()? {
            let (upstream, columns): (Bound<'_, PyAny>, Bound<'_, PyAny>) = item?.extract()?;
            upstreams.push((upstream.str()?.extract()?, column_names(&columns)?));
        }
    }
    let mut calls_functions: bool = false;
    for reference in model.getattr("references")?.try_iter()? {
        let kind: Bound<'_, PyAny> = reference?.getattr("ref_kind")?;
        if kind.eq(&classes.udf_kind)? || kind.eq(&classes.table_function_kind)? {
            calls_functions = true;
            break;
        }
    }
    Ok(MetadataModel {
        name: model.getattr("name")?.extract()?,
        query_sql: model.getattr("query_sql")?.extract()?,
        authored_sql: model.getattr("authored_sql")?.extract()?,
        checked: checked(classes, model)?,
        calls_functions,
        references,
        cursor_inputs: upstreams,
        cursor: text(&get("cursor")?)?,
        cursor_type: text(&get("cursor_type")?)?,
        audits: metadata_audits(model)?,
    })
}

fn metadata_audits(model: &Bound<'_, PyAny>) -> PyResult<Vec<MetadataAudit>> {
    let entry: Bound<'_, PyAny> = model.getattr("schema_entry")?;
    if entry.is_none() {
        return Ok(Vec::new());
    }
    let py: Python<'_> = model.py();
    let mut attached: Vec<(Option<String>, Bound<'_, PyAny>)> = Vec::new();
    for audit in entry.getattr("audits")?.try_iter()? {
        attached.push((None, audit?));
    }
    for column in entry.getattr("columns")?.try_iter()? {
        let column: Bound<'_, PyAny> = column?;
        let name: String = column.getattr("name")?.extract()?;
        for audit in column.getattr("audits")?.try_iter()? {
            attached.push((Some(name.clone()), audit?));
        }
    }
    let empty: Bound<'_, PyAny> = PyString::new(py, "").into_any();
    let mut audits: Vec<MetadataAudit> = Vec::with_capacity(attached.len());
    for (column, audit) in attached {
        let arguments: Bound<'_, PyAny> = audit.getattr("arguments")?;
        let values: Bound<'_, PyAny> = arguments.call_method1("get", ("values",))?;
        let values: Option<Vec<AuditValue>> =
            if values.is_instance_of::<PyList>() || values.is_instance_of::<PyTuple>() {
                Some(
                    values
                        .try_iter()?
                        .map(|value| audit_value(&value?))
                        .collect::<PyResult<_>>()?,
                )
            } else {
                None
            };
        audits.push(MetadataAudit {
            column,
            definition: audit.getattr("definition_name")?.extract()?,
            expression: text(&arguments.call_method1("get", ("expression",))?)?,
            target: arguments
                .call_method1("get", ("to", &empty))?
                .str()?
                .extract()?,
            field: arguments
                .call_method1("get", ("field", &empty))?
                .str()?
                .extract()?,
            values,
        });
    }
    Ok(audits)
}

/// An accepted value by Python type: null, bool, number, text or other.
fn audit_value(value: &Bound<'_, PyAny>) -> PyResult<AuditValue> {
    if value.is_none() {
        return Ok(AuditValue::Null);
    }
    if value.is_instance_of::<PyBool>() {
        return Ok(AuditValue::Bool(value.is_truthy()?));
    }
    if value.is_instance_of::<PyInt>() || value.is_instance_of::<PyFloat>() {
        return Ok(AuditValue::Number(value.str()?.extract()?));
    }
    if value.is_instance_of::<PyString>() {
        return Ok(AuditValue::Text(value.extract()?));
    }
    Ok(AuditValue::Other)
}
