//! Fast lineage for unresolved root stars and models without compact facts.

use std::sync::Arc;

use polyglot_sql::ParseOptions;
use rayon::ThreadPool;
use rayon::prelude::{IntoParallelRefIterator, ParallelIterator};
use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::lineage::_helpers::parsed_lineage::{
    ParsedModel, parsed_model_lineage, proxy_parse_options,
};
use crate::lineage::_helpers::references::physical_resources;
use crate::lineage::_helpers::stars::{schema_mapping, star_lineage};
use crate::lineage::main::parser_dialect::parser_dialect;
use crate::lineage::models::{
    FastLineageModel, FastLineageOutcome, FastLineageRequest, LineageDeferral,
};
use crate::semantic_validation::models::ProjectCatalog;

/// One outcome per model, in request order, run on the compile's deep-stack analysis pool.
pub fn build_fast_lineage(
    request: &FastLineageRequest,
    catalog: &ProjectCatalog,
) -> Result<Vec<FastLineageOutcome>, String> {
    let pool: Arc<ThreadPool> = catalog.analysis_pool()?;
    Ok(pool.install(|| model_outcomes(request)))
}

/// A parser panic defers only its own model.
fn model_outcomes(request: &FastLineageRequest) -> Vec<FastLineageOutcome> {
    let schema = schema_mapping(&request.schema);
    let dialect = parser_dialect(request.dialect.as_deref());
    let options: Result<ParseOptions, serde_json::Error> = proxy_parse_options();
    request
        .models
        .par_iter()
        .map(|model| match model {
            FastLineageModel::StarExpansion {
                query_sql,
                existing_columns,
            } => FastLineageOutcome::StarColumns(star_lineage(
                &schema,
                &physical_resources(query_sql),
                existing_columns.iter().map(String::as_str),
            )),
            FastLineageModel::Parse {
                query_sql,
                inferred_columns,
            } => {
                let model = ParsedModel {
                    query_sql,
                    inferred_names: inferred_columns,
                    schema: &schema,
                    dialect,
                    options: &options,
                };
                catch_compiler_panic(|| Ok(parsed_model_lineage(&model)))
                    .unwrap_or(FastLineageOutcome::Deferred(LineageDeferral::NativeFailure))
            }
        })
        .collect()
}
