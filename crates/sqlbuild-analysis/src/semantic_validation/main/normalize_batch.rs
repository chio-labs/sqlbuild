use rayon::ThreadPool;
use rayon::iter::{IntoParallelIterator, ParallelIterator};

use crate::semantic_validation::types::NormalizationRequest;
use sqlbuild_core::panics::main::catch_compiler_panic;

/// Normalize every request, keeping each failure in place so callers raise the first in order.
pub fn normalize_analysis_sqls(
    dialect: &str,
    requests: Vec<NormalizationRequest>,
    pool: Option<&ThreadPool>,
) -> Vec<Result<String, String>> {
    let normalize = |(sql, stubs, placeholders): NormalizationRequest| {
        catch_compiler_panic(|| {
            crate::semantic_validation::_helpers::normalization::normalize_analysis_sql(
                &sql,
                dialect,
                stubs,
                placeholders,
            )
        })
    };
    match pool {
        Some(pool) => pool.install(|| requests.into_par_iter().map(normalize).collect()),
        None => requests.into_iter().map(normalize).collect(),
    }
}
