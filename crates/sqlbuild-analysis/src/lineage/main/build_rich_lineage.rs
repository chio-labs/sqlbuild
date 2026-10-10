//! Rich column lineage: Python's polyglot `analyze_query` path, answered natively.

use std::collections::HashSet;

use polyglot_sql::DialectType;
use rayon::prelude::{IntoParallelRefIterator, ParallelIterator};
use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::lineage::_helpers::dialects::is_compiled_dialect;
use crate::lineage::_helpers::references::{physical_resource_name, physical_resources};
use crate::lineage::_helpers::rich_lineage::{RichContext, rich_model_lineage, schema_names};
use crate::lineage::_helpers::stars::schema_mapping;
use crate::lineage::constants::{RICH_LINEAGE_WORKER_STACK_BYTES, RICH_LINEAGE_WORKERS};
use crate::lineage::models::{
    LineageDeferral, LineageSchemaResource, RichLineageOutcome, RichLineageRequest,
};

/// One outcome per model, in request order. A parser panic defers only its own model.
pub fn build_rich_lineage(request: &RichLineageRequest) -> Result<Vec<RichLineageOutcome>, String> {
    if request.models.is_empty() {
        return Ok(Vec::new());
    }
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
    let context = RichContext::new(
        analysis_dialect(&request.dialect),
        &request.schema,
        &referenced,
        schema_mapping(&names),
    );
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(RICH_LINEAGE_WORKERS.min(request.models.len()))
        .stack_size(RICH_LINEAGE_WORKER_STACK_BYTES)
        .thread_name(|index| format!("sqlbuild-rich-lineage-{index}"))
        .build()
        .map_err(|error| error.to_string())?;
    Ok(pool.install(|| {
        request
            .models
            .par_iter()
            .map(|query_sql| {
                catch_compiler_panic(|| Ok(rich_model_lineage(query_sql, &context)))
                    .unwrap_or(RichLineageOutcome::Deferred(LineageDeferral::NativeFailure))
            })
            .collect()
    }))
}

/// The wheel decodes the options' dialect with serde; this build may not carry it.
fn analysis_dialect(name: &str) -> Option<DialectType> {
    let Ok(dialect) =
        serde_json::from_value::<DialectType>(serde_json::Value::String(name.to_owned()))
    else {
        return None;
    };
    is_compiled_dialect(dialect).then_some(dialect)
}
