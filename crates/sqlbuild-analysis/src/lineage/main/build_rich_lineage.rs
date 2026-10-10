//! Rich column lineage: Python's polyglot `analyze_query` path, answered natively.

use std::collections::HashSet;

use polyglot_sql::DialectType;

use crate::lineage::_helpers::references::{physical_resource_name, physical_resources};
use crate::lineage::_helpers::rich_lineage::{
    RichContext, outcomes_in_order, rich_model_lineage, schema_names,
};
use crate::lineage::_helpers::stars::schema_mapping;
use crate::lineage::constants::{RICH_LINEAGE_WORKER_STACK_BYTES, RICH_LINEAGE_WORKERS};
use crate::lineage::main::parser_dialect::parser_dialect;
use crate::lineage::models::{LineageSchemaResource, RichLineageOutcome, RichLineageRequest};

/// One outcome per model, in request order; a parser panic fails the whole request.
pub fn build_rich_lineage(request: &RichLineageRequest) -> Result<Vec<RichLineageOutcome>, String> {
    if request.models.is_empty() {
        return Ok(Vec::new());
    }
    let Some(dialect) = parser_dialect(Some(&request.dialect)) else {
        return Err(format!("Unknown dialect: {}", request.dialect));
    };
    let context = request_context(request, dialect);
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(RICH_LINEAGE_WORKERS.min(request.models.len()))
        .stack_size(RICH_LINEAGE_WORKER_STACK_BYTES)
        .thread_name(|index| format!("sqlbuild-rich-lineage-{index}"))
        .build()
        .map_err(|error| error.to_string())?;
    pool.install(|| {
        outcomes_in_order(&request.models, |query_sql| {
            rich_model_lineage(query_sql, &context)
        })
    })
}

/// The shared context: only tables some model references are built.
fn request_context(request: &RichLineageRequest, dialect: DialectType) -> RichContext {
    let referenced: HashSet<String> = request
        .models
        .iter()
        .flat_map(|query_sql| physical_resources(query_sql))
        .map(|resource| resource.physical_name)
        .collect();
    let names: Vec<LineageSchemaResource> = request
        .schema
        .iter()
        .map(schema_names)
        .filter(|resource| {
            referenced.contains(&physical_resource_name(
                resource.resource_type,
                &resource.name,
            ))
        })
        .collect();
    RichContext::new(
        dialect,
        &request.schema,
        &referenced,
        schema_mapping(&names),
    )
}
