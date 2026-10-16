//! A compiled model's analysis outcomes as Rust data: views read their owner, records their fields.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};

use crate::bindings::_helpers::compiled_project::compiled_model_view::{
    DeclaredRow, InferredRow, LineageInput, NativeCompiledModel,
};

/// Each inferred output column as `(name, type, nullability)`, `None` when none were inferred.
pub(crate) fn inferred_rows(model: &Bound<'_, PyAny>) -> PyResult<Option<Vec<InferredRow>>> {
    if let Ok(view) = model.downcast::<NativeCompiledModel>() {
        return view.get().inferred_rows(model.py());
    }
    let rows: Bound<'_, PyAny> = model.getattr("inferred_rows")?;
    if rows.is_none() {
        return Ok(None);
    }
    let mut inferred: Vec<InferredRow> = Vec::new();
    for row in rows.try_iter()? {
        let (name, column_type, nullability): (String, Option<String>, Bound<'_, PyAny>) =
            row?.extract()?;
        inferred.push((name, column_type, nullability.str()?.extract()?));
    }
    Ok(Some(inferred))
}

/// The names of the inferred output columns, `None` when the shape is unknown.
pub(crate) fn inferred_names(model: &Bound<'_, PyAny>) -> PyResult<Option<Vec<String>>> {
    Ok(inferred_rows(model)?.map(column_names))
}

fn column_names(rows: Vec<InferredRow>) -> Vec<String> {
    rows.into_iter().map(|(name, _, _)| name).collect()
}

/// Each declared column of the attached schema as `(name, type)`, `None` without a schema.
pub(crate) fn declared_rows(model: &Bound<'_, PyAny>) -> PyResult<Option<Vec<DeclaredRow>>> {
    if let Ok(view) = model.downcast::<NativeCompiledModel>() {
        return view.get().schema_column_rows(model.py());
    }
    model.getattr("schema_column_rows")?.extract()
}

/// Whether the attached schema declares dynamic column families.
pub(crate) fn dynamic_columns_declared(model: &Bound<'_, PyAny>) -> PyResult<bool> {
    if let Ok(view) = model.downcast::<NativeCompiledModel>() {
        return view.get().dynamic_columns_declared(model.py());
    }
    model.getattr("has_dynamic_columns")?.is_truthy()
}

/// `(has star, star resolved)` of the model's analysed query.
pub(crate) fn star_flags(model: &Bound<'_, PyAny>) -> PyResult<(bool, bool)> {
    if let Ok(view) = model.downcast::<NativeCompiledModel>() {
        let view: &NativeCompiledModel = view.get();
        return Ok((
            view.fast_lineage_has_star(model.py())?,
            view.fast_lineage_star_resolved(model.py())?,
        ));
    }
    Ok((
        model.getattr("fast_lineage_has_star")?.is_truthy()?,
        model.getattr("fast_lineage_star_resolved")?.is_truthy()?,
    ))
}

/// Output columns whose types semantic recovery forgot, in any order.
pub(crate) fn unchecked_columns(model: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    if let Ok(view) = model.downcast::<NativeCompiledModel>() {
        return Ok(view.get().unchecked_columns().to_vec());
    }
    model
        .getattr("unchecked_output_columns")?
        .try_iter()?
        .map(|column| column?.extract())
        .collect()
}

/// Each lineage output with the `(resource, column)` pairs it reads; empty without lineage.
pub(crate) fn lineage_inputs(model: &Bound<'_, PyAny>) -> PyResult<Vec<LineageInput>> {
    if let Ok(view) = model.downcast::<NativeCompiledModel>() {
        return Ok(view.get().lineage_inputs(model.py())?.unwrap_or_default());
    }
    let columns: Bound<'_, PyAny> = model.getattr("fast_lineage_columns")?;
    if !columns.is_truthy()? {
        return Ok(Vec::new());
    }
    let mut lineage: Vec<LineageInput> = Vec::new();
    for output in columns.try_iter()? {
        let output: Bound<'_, PyAny> = output?;
        let mut upstream: Vec<(String, String)> = Vec::new();
        for source in output.getattr("upstream_columns")?.try_iter()? {
            let source: Bound<'_, PyAny> = source?;
            upstream.push((
                source.getattr("resource_name")?.extract()?,
                source.getattr("column_name")?.extract()?,
            ));
        }
        lineage.push((output.getattr("output_column")?.extract()?, upstream));
    }
    Ok(lineage)
}

/// Whether the native session validated the model's bindings.
pub(crate) fn binding_validated(model: &Bound<'_, PyAny>) -> PyResult<bool> {
    if let Ok(view) = model.downcast::<NativeCompiledModel>() {
        return view.get().binding_validated(model.py());
    }
    model.getattr("binding_validated")?.is_truthy()
}

/// Whether the model's dynamic pivot proof proved its output columns.
pub(crate) fn output_proven(model: &Bound<'_, PyAny>) -> PyResult<bool> {
    if let Ok(view) = model.downcast::<NativeCompiledModel>() {
        return view.get().output_proven(model.py());
    }
    let proof: Bound<'_, PyAny> = model.getattr("dynamic_column_contract")?;
    Ok(!proof.is_none() && proof.getattr("output_proven")?.is_truthy()?)
}
