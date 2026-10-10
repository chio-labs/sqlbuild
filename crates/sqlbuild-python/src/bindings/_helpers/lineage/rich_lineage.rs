//! Rich column lineage for the preview compiler engine.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::lineage::main::build_rich_lineage::build_rich_lineage;
use sqlbuild_analysis::lineage::models::{
    LineageResourceType, LineageSource, RichLineageColumn, RichLineageOutcome, RichLineageRequest,
    RichSchemaResource,
};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::types::CompilerDetach;

type TypedColumns = Vec<(String, Option<String>)>;
type SourceRow = (&'static str, String, String);
type ColumnRow = (
    String,
    &'static str,
    &'static str,
    &'static str,
    Vec<SourceRow>,
);
/// `(dialect, [(resource_type, name, assigned, defaulted)], [query_sql])`.
type RichRequestInput = (
    String,
    Vec<(String, String, TypedColumns, TypedColumns)>,
    Vec<String>,
);
/// `(status, columns, has_star, detail)`: detail is the polyglot error or the deferral kind.
type OutcomeRow = (&'static str, Vec<ColumnRow>, bool, Option<String>);

/// Build rich lineage for the requested models' SQL, in request order.
#[pyfunction]
fn build_rich_column_lineage(
    py: Python<'_>,
    request: RichRequestInput,
) -> PyResult<Vec<OutcomeRow>> {
    let (dialect, schema, models) = request;
    let schema: Vec<RichSchemaResource> = schema
        .into_iter()
        .map(schema_resource)
        .collect::<PyResult<_>>()?;
    let request = RichLineageRequest {
        dialect,
        schema,
        models,
    };
    let outcomes: Vec<RichLineageOutcome> = py
        .compiler_detach(|| build_rich_lineage(&request))
        .map_err(compiler_error)?;
    Ok(outcomes.into_iter().map(outcome_row).collect())
}

fn schema_resource(
    (resource_type, name, assigned, defaulted): (String, String, TypedColumns, TypedColumns),
) -> PyResult<RichSchemaResource> {
    let Some(kind) = LineageResourceType::from_value(&resource_type) else {
        return Err(PyValueError::new_err(format!(
            "unknown resource: {resource_type}"
        )));
    };
    Ok(RichSchemaResource {
        resource_type: kind,
        name,
        assigned,
        defaulted,
    })
}

fn outcome_row(outcome: RichLineageOutcome) -> OutcomeRow {
    let (status, columns, has_star, detail) = outcome.into_parts();
    (
        status,
        columns.into_iter().map(column_row).collect(),
        has_star,
        detail,
    )
}

fn column_row(column: RichLineageColumn) -> ColumnRow {
    let RichLineageColumn {
        column,
        nullability,
    } = column;
    (
        column.output_column,
        column.transform_kind.as_str(),
        column.confidence.as_str(),
        nullability.as_str(),
        column
            .upstream_columns
            .into_iter()
            .map(source_row)
            .collect(),
    )
}

fn source_row(source: LineageSource) -> SourceRow {
    (
        source.resource_type.as_str(),
        source.resource_name,
        source.column_name,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_rich_column_lineage, module)?)?;
    Ok(())
}
