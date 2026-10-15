//! A `CompiledModel` for a model input built outside the native compile-input stage.

use crate::bindings::_helpers::compiler_records::shape_classes::shape_class;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyList, PyString, PyTuple};

const NATIVE_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS_MODULE: &str = "sqlbuild._native";
const COMPILE_TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";
const LINEAGE_TYPES_MODULE: &str = "sqlbuild.compiler.lineage.types";
const CONTRACT_MODELS_MODULE: &str = "sqlbuild._native";

type Object<'py> = Bound<'py, PyAny>;

/// The compiled model of `model_input` from its session outcome, fallback rows and proof.
pub(crate) fn compiled_model<'py>(
    model_input: &Object<'py>,
    deps: &Object<'py>,
    analysis: &Object<'py>,
    macro_deps: &Object<'py>,
) -> PyResult<Object<'py>> {
    let py: Python<'py> = model_input.py();
    let native = py.import(NATIVE_MODULE)?;
    let models = py.import(COMPILE_MODELS_MODULE)?;
    let types = py.import(COMPILE_TYPES_MODULE)?;
    let model_file: Object<'py> = model_input.getattr("model_file")?;
    let model_name: Object<'py> = model_file.getattr("file_path")?.getattr("stem")?;
    let none: Object<'py> = py.None().into_bound(py);
    let mut inferred: Object<'py> = none.clone();
    let mut lineage: Object<'py> = none.clone();
    let mut has_star: Object<'py> = false_object(py);
    let mut star_resolved: Object<'py> = false_object(py);
    let mut diagnostics: Object<'py> = PyTuple::empty(py).into_any();
    let mut validated: Object<'py> = false_object(py);
    let mut proof: Object<'py> = native
        .getattr("dynamic_contract_proof")?
        .call1((analysis.getattr("standalone_proof")?,))?;
    let session: Object<'py> = analysis.getattr("session")?;
    if !session.is_none() {
        let (session, position): (Object<'py>, Object<'py>) = session.extract()?;
        let arguments: Bound<'py, PyDict> = PyDict::new(py);
        arguments.set_item("session", session)?;
        arguments.set_item("position", position)?;
        arguments.set_item("placeholders", &none)?;
        let outcome: Object<'py> = native
            .getattr("session_outcome_analysis")?
            .call((), Some(&arguments))?;
        let result: Object<'py> = outcome.getattr("polyglot_analysis")?;
        if result.getattr("analysis_succeeded")?.is_truthy()? {
            inferred = result.getattr("columns")?;
            lineage = result.getattr("lineage_columns")?;
            has_star = result.getattr("has_star")?;
            star_resolved = result.getattr("star_resolved")?;
        } else {
            inferred = fallback_columns(&analysis.getattr("fallback")?)?;
        }
        let session_proof: Object<'py> = outcome.getattr("dynamic_column_contract")?;
        if session_proof.is_truthy()? {
            proof = session_proof;
        }
        validated = result.getattr("binding_validated")?;
        let cleaned: Object<'py> = outcome.getattr("cleaned_sql")?;
        let cleaned: Object<'py> = if cleaned.is_truthy()? {
            cleaned
        } else {
            PyString::new(py, "").into_any()
        };
        diagnostics = located(
            model_input,
            &result.getattr("binding_diagnostics")?,
            &cleaned,
        )?;
    }
    if !proof.is_none() && proof.getattr("output_proven")?.is_truthy()? {
        inferred = proof.getattr("fixed_columns")?;
        has_star = true_object(py);
    }
    let resource_type: Object<'py> = types.getattr("CompiledResourceType")?;
    let key_class: Object<'py> = models.getattr("CompiledObjectKey")?;
    let mut dependency_keys: Vec<Object<'py>> = Vec::new();
    for dependency in deps.try_iter()? {
        let (kind, name): (Object<'py>, Object<'py>) = dependency?.extract()?;
        dependency_keys.push(call(
            &key_class,
            &[
                ("resource_type", resource_type.call1((kind,))?),
                ("name", name),
            ],
        )?);
    }
    let config: Object<'py> = model_input.getattr("config")?;
    let key: Object<'py> = call(
        &key_class,
        &[
            ("resource_type", resource_type.getattr("MODEL")?),
            ("name", model_name.clone()),
        ],
    )?;
    call(
        &models.getattr("CompiledModel")?,
        &[
            ("key", key),
            ("deps", PyTuple::new(py, dependency_keys)?.into_any()),
            ("name", model_name.clone()),
            ("relative_path", model_file.getattr("relative_path")?),
            ("query_sql", model_input.getattr("query_sql")?),
            ("config", config.clone()),
            ("destination", destination(&config, &model_name)?),
            ("references", model_input.getattr("references")?),
            ("schema_entry", model_input.getattr("schema_entry")?),
            ("inferred_columns", inferred),
            ("fast_lineage_columns", lineage),
            ("fast_lineage_has_star", has_star),
            ("fast_lineage_star_resolved", star_resolved),
            ("authored_sql", model_file.getattr("contents")?),
            ("authored_query_sql", model_file.getattr("query_sql")?),
            (
                "output_column_locations",
                model_file.getattr("output_column_locations")?,
            ),
            (
                "extract_implicit_alias_columns",
                model_file.getattr("extract_implicit_alias_columns")?,
            ),
            ("macro_deps", macro_deps.clone()),
            (
                "enum_declarations",
                model_input.getattr("enum_declarations")?,
            ),
            (
                "constant_declarations",
                model_input.getattr("constant_declarations")?,
            ),
            ("enum_columns", model_input.getattr("enum_columns")?),
            ("binding_diagnostics", diagnostics),
            ("binding_validated", validated),
            ("dynamic_column_contract", proof),
            (
                "rejected_sql_analysis_opt_out",
                model_input.getattr("rejected_sql_analysis_opt_out")?,
            ),
        ],
    )
}

fn false_object(py: Python<'_>) -> Object<'_> {
    pyo3::types::PyBool::new(py, false).to_owned().into_any()
}

fn true_object(py: Python<'_>) -> Object<'_> {
    pyo3::types::PyBool::new(py, true).to_owned().into_any()
}

/// A model's configured physical and logical destination.
fn destination<'py>(config: &Object<'py>, model_name: &Object<'py>) -> PyResult<Object<'py>> {
    let py: Python<'py> = config.py();
    let values: Object<'py> = config.getattr("values")?;
    let text = |key: &str| -> PyResult<Option<Object<'py>>> {
        let value: Object<'py> = values.call_method1("get", (key,))?;
        Ok(value.is_instance_of::<PyString>().then_some(value))
    };
    let none: Object<'py> = py.None().into_bound(py);
    call(
        &py.import(COMPILE_MODELS_MODULE)?
            .getattr("CompiledRelationLocation")?,
        &[
            (
                "database",
                text("database")?.unwrap_or_else(|| none.clone()),
            ),
            ("schema", text("schema")?.unwrap_or_else(|| none.clone())),
            ("name", text("alias")?.unwrap_or_else(|| model_name.clone())),
            ("qualified_name", none.clone()),
            ("logical_schema", config.getattr("logical_schema")?),
            ("logical_database", config.getattr("logical_database")?),
        ],
    )
}

/// A failed analysis's parse-mode column rows as inferred columns, None without rows.
fn fallback_columns<'py>(rows: &Object<'py>) -> PyResult<Object<'py>> {
    let py: Python<'py> = rows.py();
    if rows.is_none() {
        return Ok(rows.clone());
    }
    let column_class: Object<'py> = py
        .import(COMPILE_MODELS_MODULE)?
        .getattr("InferredColumn")?;
    let nullability: Object<'py> = py
        .import(LINEAGE_TYPES_MODULE)?
        .getattr("InferredNullability")?;
    let mut columns: Vec<Object<'py>> = Vec::new();
    for row in rows.try_iter()? {
        let (name, data_type, value): (Object<'py>, Object<'py>, Object<'py>) = row?.extract()?;
        columns.push(call(
            &column_class,
            &[
                ("name", name),
                ("type", data_type),
                ("nullability", nullability.call1((value,))?),
            ],
        )?);
    }
    Ok(PyTuple::new(py, columns)?.into_any())
}

/// Binding diagnostics located in the authored model file.
fn located<'py>(
    model_input: &Object<'py>,
    diagnostics: &Object<'py>,
    cleaned: &Object<'py>,
) -> PyResult<Object<'py>> {
    let py: Python<'py> = model_input.py();
    if !diagnostics.is_truthy()? {
        return Ok(PyTuple::empty(py).into_any());
    }
    let model_file: Object<'py> = model_input.getattr("model_file")?;
    let path: Object<'py> = model_file.getattr("relative_path")?;
    let mut rows: Vec<Object<'py>> = Vec::new();
    for item in diagnostics.try_iter()? {
        let item: Object<'py> = item?;
        let fields: Vec<Object<'py>> = [
            "code", "message", "line", "column", "start", "end", "severity",
        ]
        .into_iter()
        .map(|name| item.getattr(name))
        .collect::<PyResult<_>>()?;
        rows.push(PyTuple::new(py, fields)?.into_any());
    }
    let texts: Object<'py> = PyTuple::new(
        py,
        [
            model_file.getattr("contents")?,
            model_file.getattr("query_sql")?,
            cleaned.clone(),
        ],
    )?
    .into_any();
    let expansion: Object<'py> = model_input.getattr("sql_expansion")?;
    let expansion_row: Object<'py> = if expansion.is_none() {
        expansion
    } else {
        let mut passes: Vec<Object<'py>> = Vec::new();
        for spans in expansion.getattr("passes")?.try_iter()? {
            let mut rows: Vec<Object<'py>> = Vec::new();
            for span in spans?.try_iter()? {
                let span: Object<'py> = span?;
                let fields: Vec<Object<'py>> =
                    ["source_start", "source_end", "output_start", "output_end"]
                        .into_iter()
                        .map(|name| span.getattr(name))
                        .collect::<PyResult<_>>()?;
                rows.push(PyTuple::new(py, fields)?.into_any());
            }
            passes.push(PyList::new(py, rows)?.into_any());
        }
        PyTuple::new(
            py,
            [
                expansion.getattr("expanded_sql")?,
                PyList::new(py, passes)?.into_any(),
            ],
        )?
        .into_any()
    };
    let located: Object<'py> = py
        .import(NATIVE_MODULE)?
        .getattr("locate_model_binding_diagnostics")?
        .call1((PyList::new(py, rows)?, texts, expansion_row))?;
    let models = py.import(COMPILE_MODELS_MODULE)?;
    let types = py.import(COMPILE_TYPES_MODULE)?;
    let diagnostic_class: Object<'py> = models.getattr("CompilerDiagnostic")?;
    let location_class: Object<'py> = py
        .import(CONTRACT_MODELS_MODULE)?
        .getattr("SourceLocation")?;
    let phase: Object<'py> = shape_class(types.as_any(), "DiagnosticPhase")?.getattr("COMPILE")?;
    let model: Object<'py> = types.getattr("CompiledResourceType")?.getattr("MODEL")?;
    let name: Object<'py> = model_file.getattr("file_path")?.getattr("stem")?;
    let mut built: Vec<Object<'py>> = Vec::new();
    for row in located.try_iter()? {
        let (code, message, severity, line, column, span): (
            Object<'py>,
            Object<'py>,
            Object<'py>,
            Object<'py>,
            Object<'py>,
            Object<'py>,
        ) = row?.extract()?;
        let location: Object<'py> = if span.is_none() {
            span
        } else {
            call(
                &location_class,
                &[
                    ("path", path.clone()),
                    ("line", span.get_item(0)?),
                    ("column", span.get_item(1)?),
                    ("end_line", span.get_item(2)?),
                    ("end_column", span.get_item(3)?),
                ],
            )?
        };
        built.push(call(
            &diagnostic_class,
            &[
                ("phase", phase.clone()),
                ("severity", severity),
                ("code", code),
                ("message", message),
                ("resource_type", model.clone()),
                ("resource_name", name.clone()),
                ("path", path.clone()),
                ("line", line),
                ("column", column),
                ("location", location),
            ],
        )?);
    }
    Ok(PyTuple::new(py, built)?.into_any())
}

fn call<'py>(callable: &Object<'py>, pairs: &[(&str, Object<'py>)]) -> PyResult<Object<'py>> {
    let arguments: Bound<'py, PyDict> = PyDict::new(callable.py());
    for (name, value) in pairs {
        arguments.set_item(*name, value)?;
    }
    callable.call((), Some(&arguments))
}
