//! Native audit, SQL test and SQL hook SQL checks against the closed model shapes.

use std::sync::Arc;

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyRef, PyResult, Python,
};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyList, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::semantic_checks::main::resource_sql_diagnostics::resource_sql_diagnostics;
use sqlbuild_analysis::semantic_checks::models::{
    AuditSqlInput, HookModelInput, HookSqlInput, ResourceSqlDiagnostic, ResourceSqlFailure,
    ResourceSqlKind, ResourceSqlRequest, SqlTestSqlInput,
};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::models::ProjectCatalog;
use crate::bindings::types::CompilerDetach;

const COMPILE_ERRORS_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const CONTRACT_MODELS_MODULE: &str = "sqlbuild._native";
const SQL_ANALYSIS_CONFIG_KEY: &str = "sql_analysis";
const MODEL_HOOK_KEYS: [&str; 2] = ["pre_hooks", "post_hooks"];
const BUILT_IN_AUDIT_ROOT: &str = "<built-in>";
const UDF_KIND: &str = "udf";
const TABLE_FUNCTION_KIND: &str = "table_fn";
const TABLE_FUNCTION_STUB_PREFIX: &str = "__sqlbuild_table_function_";

/// The compile models a resource SQL diagnostic is built from.
struct DiagnosticClasses<'py> {
    compiler_diagnostic: Bound<'py, PyAny>,
    source_location: Bound<'py, PyAny>,
    path: Bound<'py, PyAny>,
}

/// Bind the project's audit, SQL test and SQL hook bodies on `catalog` against `shapes`.
#[pyfunction]
pub(crate) fn resource_sql_diagnostics_of<'py>(
    catalog: PyRef<'_, ProjectCatalog>,
    project: &Bound<'py, PyAny>,
    shapes: &Bound<'py, PyDict>,
    profile: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = project.py();
    let request: ResourceSqlRequest = request(project, shapes, profile)?;
    let catalog = &catalog.inner;
    let outcome = py
        .compiler_detach(|| Ok(resource_sql_diagnostics(&request, catalog)))
        .map_err(compiler_error)?;
    let diagnostics: Vec<ResourceSqlDiagnostic> = match outcome {
        Ok(diagnostics) => diagnostics,
        Err(failure) => return Err(failure_error(py, failure)?),
    };
    let classes = DiagnosticClasses {
        compiler_diagnostic: py
            .import(COMPILE_MODELS_MODULE)?
            .getattr("CompilerDiagnostic")?,
        source_location: py
            .import(CONTRACT_MODELS_MODULE)?
            .getattr("SourceLocation")?,
        path: py.import("pathlib")?.getattr("Path")?,
    };
    let built: Vec<Bound<'py, PyAny>> = diagnostics
        .into_iter()
        .map(|diagnostic| python_diagnostic(py, &classes, diagnostic))
        .collect::<PyResult<_>>()?;
    PyTuple::new(py, built)
}

fn request(
    project: &Bound<'_, PyAny>,
    shapes: &Bound<'_, PyDict>,
    profile: &Bound<'_, PyAny>,
) -> PyResult<ResourceSqlRequest> {
    let py: Python<'_> = project.py();
    let reference_class: Bound<'_, PyAny> = py
        .import(COMPILE_MODELS_MODULE)?
        .getattr("CompileSqlReference")?;
    let mut audits: Vec<AuditSqlInput> = Vec::new();
    for audit in project.getattr("audits")?.try_iter()? {
        audits.push(audit_input(&audit?, &reference_class)?);
    }
    let mut sql_tests: Vec<SqlTestSqlInput> = Vec::new();
    for test in project.getattr("sql_tests")?.try_iter()? {
        sql_tests.push(sql_test_input(&test?)?);
    }
    let mut models: Vec<HookModelInput> = Vec::new();
    for model in project.getattr("models")?.try_iter()? {
        models.push(model_input(&model?, &reference_class)?);
    }
    let mut hook_files: Vec<(String, Arc<str>)> = Vec::new();
    for file in project.getattr("sql_hook_files")?.try_iter()? {
        let file: Bound<'_, PyAny> = file?;
        hook_files.push((
            file.getattr("relative_path")?.str()?.extract()?,
            Arc::from(file.getattr("contents")?.extract::<String>()?),
        ));
    }
    Ok(ResourceSqlRequest {
        dialect: profile.getattr("sql_analysis_dialect")?.extract()?,
        quoted_ignore_case: profile
            .getattr("quoted_identifiers_ignore_case")?
            .extract()?,
        require_sql_analysis: project
            .getattr("settings")?
            .getattr("require_sql_analysis")?
            .extract()?,
        shapes: shapes
            .iter()
            .map(|(name, columns)| shape(&name, &columns))
            .collect::<PyResult<_>>()?,
        audits,
        sql_tests,
        models,
        hook_files,
    })
}

/// One closed relation shape: its name and `(column, type)` pairs in order.
fn shape(
    name: &Bound<'_, PyAny>,
    columns: &Bound<'_, PyAny>,
) -> PyResult<(String, Vec<(String, String)>)> {
    let mut pairs: Vec<(String, String)> = Vec::new();
    for pair in columns.call_method0("items")?.try_iter()? {
        pairs.push(pair?.extract()?);
    }
    Ok((name.extract()?, pairs))
}

fn audit_input(
    audit: &Bound<'_, PyAny>,
    reference_class: &Bound<'_, PyAny>,
) -> PyResult<AuditSqlInput> {
    let file: Bound<'_, PyAny> = audit.getattr("audit_file")?;
    let block: Bound<'_, PyAny> = audit.getattr("audit_block")?;
    let target_name: Bound<'_, PyAny> = audit.getattr("attached_target_name")?;
    let attached_target: Option<(String, String)> = if target_name.is_none() {
        None
    } else {
        Some((
            audit.getattr("attached_target_kind")?.str()?.extract()?,
            target_name.extract()?,
        ))
    };
    let first_part: Option<String> = file
        .getattr("file_path")?
        .getattr("parts")?
        .try_iter()?
        .next()
        .transpose()?
        .map(|part| part.extract())
        .transpose()?;
    let mut bodies: Vec<(Option<String>, Option<String>)> = Vec::new();
    for attribute in ["sql_body", "measure_sql", "evidence_sql"] {
        bodies.push((
            audit.getattr(attribute)?.extract()?,
            block.getattr(attribute)?.extract()?,
        ));
    }
    Ok(AuditSqlInput {
        name: audit.getattr("name")?.extract()?,
        definition_name: audit.getattr("definition_name")?.extract()?,
        attached_target,
        attached_column: audit.getattr("attached_column_name")?.extract()?,
        built_in: first_part.as_deref() == Some(BUILT_IN_AUDIT_ROOT),
        path: file.getattr("relative_path")?.str()?.extract()?,
        contents: Arc::from(file.getattr("contents")?.extract::<String>()?),
        bodies,
        opts_out: opts_out(&block.getattr("header_values")?)?,
        relations: relations(&audit.getattr("references")?, reference_class)?,
    })
}

fn sql_test_input(test: &Bound<'_, PyAny>) -> PyResult<SqlTestSqlInput> {
    let file: Bound<'_, PyAny> = test.getattr("test_file")?;
    let block: Bound<'_, PyAny> = test.getattr("test_block")?;
    Ok(SqlTestSqlInput {
        name: test.getattr("name")?.extract()?,
        expected_model_names: test
            .getattr("expected_model_names")?
            .try_iter()?
            .map(|name| name?.extract())
            .collect::<PyResult<_>>()?,
        path: file.getattr("relative_path")?.str()?.extract()?,
        contents: Arc::from(file.getattr("contents")?.extract::<String>()?),
        sql_body: test.getattr("sql_body")?.extract()?,
        authored_body: block.getattr("sql_body")?.extract()?,
        opts_out: opts_out(&block.getattr("header_values")?)?,
    })
}

fn model_input(
    model: &Bound<'_, PyAny>,
    reference_class: &Bound<'_, PyAny>,
) -> PyResult<HookModelInput> {
    let values: Bound<'_, PyAny> = model.getattr("config")?.getattr("values")?;
    let mut hooks: Vec<HookSqlInput> = Vec::new();
    for key in MODEL_HOOK_KEYS {
        let entries: Bound<'_, PyAny> = values.call_method1("get", (key,))?;
        if !(entries.is_instance_of::<PyList>() || entries.is_instance_of::<PyTuple>()) {
            continue;
        }
        for (index, entry) in entries.try_iter()?.enumerate() {
            let entry: Bound<'_, PyAny> = entry?;
            let Some(statement) = text(&optional_attribute(&entry, "statement")?)? else {
                continue;
            };
            let hook_path: Bound<'_, PyAny> = optional_attribute(&entry, "relative_path")?;
            let reads: Bound<'_, PyAny> = optional_attribute(&entry, "reads")?;
            hooks.push(HookSqlInput {
                key: key.to_owned(),
                index,
                statement,
                hook_path: if hook_path.is_none() {
                    None
                } else {
                    Some(hook_path.str()?.extract()?)
                },
                definition: text(&optional_attribute(&entry, "definition_sql")?)?,
                relations: if reads.is_truthy()? {
                    relations(&reads, reference_class)?
                } else {
                    Vec::new()
                },
            });
        }
    }
    Ok(HookModelInput {
        name: model.getattr("name")?.extract()?,
        path: model.getattr("relative_path")?.str()?.extract()?,
        authored_sql: Arc::from(model.getattr("authored_sql")?.extract::<String>()?),
        analysis_disabled: opts_out(&values)?,
        hooks,
    })
}

/// The value when it is a `str`, otherwise `None`.
fn text(value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_instance_of::<PyString>() {
        return value.extract().map(Some);
    }
    Ok(None)
}

/// `getattr(value, name, None)`.
fn optional_attribute<'py>(value: &Bound<'py, PyAny>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    if value.hasattr(name)? {
        value.getattr(name)
    } else {
        Ok(value.py().None().into_bound(value.py()))
    }
}

/// Whether the values set `sql_analysis = false`.
fn opts_out(values: &Bound<'_, PyAny>) -> PyResult<bool> {
    Ok(values
        .call_method1("get", (SQL_ANALYSIS_CONFIG_KEY,))?
        .is(PyBool::new(values.py(), false)))
}

/// `sorted(binding_relation_names(...))` of the `CompileSqlReference`s among `references`.
fn relations(
    references: &Bound<'_, PyAny>,
    reference_class: &Bound<'_, PyAny>,
) -> PyResult<Vec<String>> {
    let mut names: Vec<String> = Vec::new();
    for reference in references.try_iter()? {
        let reference: Bound<'_, PyAny> = reference?;
        if !reference.is_instance(reference_class)? {
            continue;
        }
        let kind: String = reference.getattr("ref_kind")?.str()?.extract()?;
        let name: String = reference.getattr("ref_name")?.extract()?;
        if kind == UDF_KIND {
            continue;
        }
        names.push(if kind == TABLE_FUNCTION_KIND {
            format!("{TABLE_FUNCTION_STUB_PREFIX}{name}")
        } else {
            name
        });
    }
    names.sort_unstable();
    names.dedup();
    Ok(names)
}

fn python_diagnostic<'py>(
    py: Python<'py>,
    classes: &DiagnosticClasses<'py>,
    diagnostic: ResourceSqlDiagnostic,
) -> PyResult<Bound<'py, PyAny>> {
    let (line, column, end_line, end_column) = diagnostic.span;
    let location: Bound<'py, PyDict> = PyDict::new(py);
    location.set_item("path", classes.path.call1((&diagnostic.path,))?)?;
    location.set_item("line", line)?;
    location.set_item("column", column)?;
    location.set_item("end_line", end_line)?;
    location.set_item("end_column", end_column)?;
    let fields: Bound<'py, PyDict> = PyDict::new(py);
    fields.set_item("phase", "compile")?;
    fields.set_item(
        "severity",
        if diagnostic.is_error {
            "error"
        } else {
            "warning"
        },
    )?;
    fields.set_item("code", diagnostic.code)?;
    fields.set_item("message", diagnostic.message)?;
    fields.set_item(
        "resource_type",
        match diagnostic.kind {
            ResourceSqlKind::Audit => "audit",
            ResourceSqlKind::SqlTest => "sql_test",
            ResourceSqlKind::Model => "model",
        },
    )?;
    fields.set_item("resource_name", diagnostic.resource_name)?;
    fields.set_item(
        "location",
        classes.source_location.call((), Some(&location))?,
    )?;
    fields.set_item("notes", PyTuple::new(py, diagnostic.note)?)?;
    fields.set_item("help", diagnostic.help)?;
    classes.compiler_diagnostic.call((), Some(&fields))
}

fn failure_error(py: Python<'_>, failure: ResourceSqlFailure) -> PyResult<PyErr> {
    Ok(match failure {
        ResourceSqlFailure::CursorIntrinsic(message) => PyErr::from_value(
            py.import(COMPILE_ERRORS_MODULE)?
                .getattr("CompileInputError")?
                .call1((message,))?,
        ),
        ResourceSqlFailure::Normalization(message) | ResourceSqlFailure::Internal(message) => {
            compiler_error(message)
        }
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resource_sql_diagnostics_of, module)?)
}
