//! The worker pool native discovery runs on; header parsing recurses, so stacks are large.

use rayon::{ThreadPool, ThreadPoolBuilder};
use std::sync::OnceLock;

const WORKER_STACK_BYTES: usize = 16 * 1024 * 1024;

static POOL: OnceLock<Result<ThreadPool, String>> = OnceLock::new();

pub(crate) fn discovery_pool() -> Result<&'static ThreadPool, String> {
    POOL.get_or_init(|| {
        ThreadPoolBuilder::new()
            .stack_size(WORKER_STACK_BYTES)
            .thread_name(|index| format!("sqlbuild-discovery-{index}"))
            .build()
            .map_err(|error| error.to_string())
    })
    .as_ref()
    .map_err(Clone::clone)
}
