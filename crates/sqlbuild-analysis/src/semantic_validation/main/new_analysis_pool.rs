use crate::semantic_validation::_helpers::catalog;

/// A deep-stack analysis pool, for work that runs without a compile's catalog.
pub fn new_analysis_pool() -> Result<rayon::ThreadPool, String> {
    catalog::new_analysis_pool()
}
