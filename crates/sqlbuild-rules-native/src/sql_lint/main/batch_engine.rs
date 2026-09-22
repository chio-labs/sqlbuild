use crate::sql_lint::_helpers::engine::lint;
use crate::sql_lint::models::{LintRequest, LintResponse};
use rayon::iter::{IntoParallelIterator, ParallelIterator};

pub(crate) fn lint_batch_json(request_json: &str) -> Result<String, String> {
    let requests: Vec<LintRequest> =
        serde_json::from_str(request_json).map_err(|error| error.to_string())?;
    if requests.is_empty() {
        return Ok("[]".to_owned());
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(requests.len().min(4))
        .stack_size(16 * 1024 * 1024)
        .build()
        .map_err(|error| error.to_string())?;
    let results: Vec<Result<LintResponse, String>> =
        pool.install(|| requests.into_par_iter().map(lint).collect());
    serde_json::to_string(&results).map_err(|error| error.to_string())
}
