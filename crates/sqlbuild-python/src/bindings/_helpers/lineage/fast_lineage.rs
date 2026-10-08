//! Fast column lineage for the preview compiler engine.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::lineage::main::build_fast_lineage::build_fast_lineage;
use sqlbuild_analysis::lineage::models::{
    FastLineageModel, FastLineageOutcome, FastLineageRequest, LineageColumn, LineageResourceType,
    LineageSchemaResource, LineageSource,
};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::types::CompilerDetach;

type SourceRow = (&'static str, String, String);
type ColumnRow = (String, &'static str, &'static str, Vec<SourceRow>);
/// `(status, columns, has_star, detail)`; see `FastLineageOutcome::into_parts`.
type OutcomeRow = (&'static str, Vec<ColumnRow>, bool, Option<String>);

/// Build fast lineage for `(star_expansion, query_sql, column_names)` models.
#[pyfunction]
fn build_fast_column_lineage(
    py: Python<'_>,
    dialect: Option<String>,
    schema: Vec<(String, String, Vec<String>)>,
    models: Vec<(bool, String, Vec<String>)>,
) -> PyResult<Vec<OutcomeRow>> {
    let schema: Vec<LineageSchemaResource> = schema
        .into_iter()
        .map(schema_resource)
        .collect::<PyResult<_>>()?;
    let models: Vec<FastLineageModel> = models.into_iter().map(lineage_model).collect();
    let request = FastLineageRequest {
        dialect,
        schema,
        models,
    };
    let outcomes = py
        .compiler_detach(|| Ok(build_fast_lineage(&request)))
        .map_err(compiler_error)?;
    Ok(outcomes.into_iter().map(outcome_row).collect())
}

fn schema_resource(
    (resource_type, name, columns): (String, String, Vec<String>),
) -> PyResult<LineageSchemaResource> {
    let Some(kind) = LineageResourceType::from_value(&resource_type) else {
        return Err(PyValueError::new_err(format!(
            "unknown resource: {resource_type}"
        )));
    };
    Ok(LineageSchemaResource {
        resource_type: kind,
        name,
        columns,
    })
}

fn lineage_model(
    (star_expansion, query_sql, names): (bool, String, Vec<String>),
) -> FastLineageModel {
    if star_expansion {
        FastLineageModel::StarExpansion {
            query_sql,
            existing_columns: names,
        }
    } else {
        FastLineageModel::Parse {
            query_sql,
            inferred_columns: names,
        }
    }
}

fn outcome_row(outcome: FastLineageOutcome) -> OutcomeRow {
    let (status, columns, has_star, detail) = outcome.into_parts();
    (status, column_rows(columns), has_star, detail)
}

fn column_rows(columns: Vec<LineageColumn>) -> Vec<ColumnRow> {
    columns
        .into_iter()
        .map(|column| {
            (
                column.output_column,
                column.transform_kind.as_str(),
                column.confidence.as_str(),
                column
                    .upstream_columns
                    .into_iter()
                    .map(source_row)
                    .collect(),
            )
        })
        .collect()
}

fn source_row(source: LineageSource) -> SourceRow {
    (
        source.resource_type.as_str(),
        source.resource_name,
        source.column_name,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_fast_column_lineage, module)?)?;
    Ok(())
}
