use crate::lineage::main::build_fast_lineage::build_fast_lineage;
use crate::lineage::models::{
    FastLineageModel, FastLineageOutcome, FastLineageRequest, LineageColumn, LineageResourceType,
    LineageSchemaResource,
};

pub(crate) fn strings(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

/// Build one model against a fixed schema: `(status, column lines, has_star, detail)`.
pub(crate) fn outcome_lines(
    dialect: Option<&str>,
    model: FastLineageModel,
) -> Vec<(&'static str, Vec<String>, bool, Option<String>)> {
    let outcomes: Vec<FastLineageOutcome> = build_fast_lineage(&FastLineageRequest {
        dialect: dialect.map(str::to_owned),
        schema: schema(),
        models: vec![model],
    });
    outcomes.into_iter().map(described_outcome).collect()
}

fn described_outcome(
    outcome: FastLineageOutcome,
) -> (&'static str, Vec<String>, bool, Option<String>) {
    let (status, columns, has_star, detail) = outcome.into_parts();
    (status, described(&columns), has_star, detail)
}

fn described(columns: &[LineageColumn]) -> Vec<String> {
    columns.iter().map(described_column).collect()
}

fn described_column(column: &LineageColumn) -> String {
    let upstream: Vec<String> = column
        .upstream_columns
        .iter()
        .map(|source| {
            format!(
                "{}:{}.{}",
                source.resource_type.as_str(),
                source.resource_name,
                source.column_name
            )
        })
        .collect();
    format!(
        "{} {} {} [{}]",
        column.output_column,
        column.transform_kind.as_str(),
        column.confidence.as_str(),
        upstream.join(" ")
    )
}

fn schema() -> Vec<LineageSchemaResource> {
    vec![
        resource(
            LineageResourceType::Model,
            "orders",
            &["order_id", "customer_id", "order_id", "amount"],
        ),
        resource(
            LineageResourceType::Model,
            "customers",
            &["customer_id", "name"],
        ),
        resource(LineageResourceType::Model, "empty", &[]),
        resource(
            LineageResourceType::Seed,
            "regions",
            &["region_id", "label"],
        ),
    ]
}

fn resource(
    resource_type: LineageResourceType,
    name: &str,
    columns: &[&str],
) -> LineageSchemaResource {
    LineageSchemaResource {
        resource_type,
        name: name.to_owned(),
        columns: strings(columns),
    }
}
