//! Fast lineage for unresolved root stars and models without compact facts.

use polyglot_sql::ParseOptions;
use rayon::prelude::{IntoParallelRefIterator, ParallelIterator};
use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::lineage::_helpers::parsed_lineage::{
    ParsedModel, lineage_dialect, parsed_model_lineage, proxy_parse_options,
};
use crate::lineage::_helpers::references::physical_resources;
use crate::lineage::_helpers::stars::{schema_mapping, star_lineage};
use crate::lineage::models::{
    FastLineageModel, FastLineageOutcome, FastLineageRequest, LineageDeferral,
};

/// One outcome per requested model, in request order; a parser panic defers only its model.
pub fn build_fast_lineage(request: &FastLineageRequest) -> Vec<FastLineageOutcome> {
    let schema = schema_mapping(&request.schema);
    let dialect = lineage_dialect(request.dialect.as_deref());
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
