use crate::lineage::main::build_rich_lineage::build_rich_lineage;
use crate::lineage::models::{
    LineageResourceType, RichLineageColumn, RichLineageOutcome, RichLineageRequest,
    RichSchemaResource,
};

/// Build one model against a fixed typed schema: `(status, column lines, has_star, detail)`.
pub(crate) fn rich_outcome(
    dialect: &str,
    sql: &str,
) -> (&'static str, Vec<String>, bool, Option<String>) {
    let request = RichLineageRequest {
        dialect: dialect.to_owned(),
        schema: rich_schema(),
        models: vec![sql.to_owned()],
    };
    let mut outcomes = build_rich_lineage(&request).expect("the rich lineage pool builds");
    assert_eq!(outcomes.len(), 1);
    match outcomes.remove(0) {
        RichLineageOutcome::Built { columns, has_star } => (
            "built",
            columns.iter().map(described_column).collect(),
            has_star,
            None,
        ),
        RichLineageOutcome::Skipped(message) => ("skipped", Vec::new(), false, Some(message)),
        RichLineageOutcome::Deferred(kind) => (
            "deferred",
            Vec::new(),
            false,
            Some(kind.as_str().to_owned()),
        ),
    }
}

fn described_column(column: &RichLineageColumn) -> String {
    let upstream: Vec<String> = column
        .column
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
        "{} {} {} {} [{}]",
        column.column.output_column,
        column.column.transform_kind.as_str(),
        column.column.confidence.as_str(),
        column.nullability.as_str(),
        upstream.join(" ")
    )
}

/// The typed schema `wheel_cases.py` gave the wheel, spelled through assigned and defaulted columns.
fn rich_schema() -> Vec<RichSchemaResource> {
    vec![
        RichSchemaResource {
            resource_type: LineageResourceType::Model,
            name: "orders".to_owned(),
            assigned: typed(&[
                ("order_id", Some("INTEGER")),
                ("customer_id", Some("TEXT")),
                ("customer_id", Some("INTEGER")),
                ("amount", Some("DOUBLE")),
            ]),
            defaulted: typed(&[("amount", Some("VARCHAR")), ("order_id", None)]),
        },
        RichSchemaResource {
            resource_type: LineageResourceType::Model,
            name: "customers".to_owned(),
            assigned: typed(&[("customer_id", Some("INTEGER"))]),
            defaulted: typed(&[("name", Some(""))]),
        },
        RichSchemaResource {
            resource_type: LineageResourceType::Model,
            name: "empty".to_owned(),
            assigned: Vec::new(),
            defaulted: Vec::new(),
        },
        RichSchemaResource {
            resource_type: LineageResourceType::Seed,
            name: "regions".to_owned(),
            assigned: typed(&[("region_id", Some("INTEGER")), ("label", Some("VARCHAR"))]),
            defaulted: Vec::new(),
        },
    ]
}

fn typed(columns: &[(&str, Option<&str>)]) -> Vec<(String, Option<String>)> {
    columns
        .iter()
        .map(|(name, column_type)| ((*name).to_owned(), column_type.map(str::to_owned)))
        .collect()
}
