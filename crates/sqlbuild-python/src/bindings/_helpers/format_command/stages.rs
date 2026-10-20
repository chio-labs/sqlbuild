//! The per-file native work of a format run: header lint and header formatting.

use std::sync::OnceLock;

use rayon::ThreadPool;
use rayon::iter::{IntoParallelRefIterator, ParallelIterator};
use sqlbuild_rules::dsl_headers::constants::RULE_HEADER_PARSE;
use sqlbuild_rules::dsl_headers::main::format_headers::format_headers;
use sqlbuild_rules::dsl_headers::main::scan_headers::scan_headers;
use sqlbuild_rules::dsl_headers::models::{HeaderRulesConfig, HeaderViolation};

use crate::bindings::_helpers::rules::dsl_headers::header_violations;
use crate::bindings::_helpers::rules::native_header_parser::NativeHeaderParser;

/// Parsers recurse deeply on nested SQL, so format workers get the stack the main thread has.
const FORMAT_WORKER_STACK_BYTES: usize = 16 * 1024 * 1024;

static FORMAT_WORKERS: OnceLock<Result<ThreadPool, String>> = OnceLock::new();

/// Run `operation` on the format worker threads, which every parallel pass inside it uses.
pub(crate) fn on_format_workers<T: Send>(
    operation: impl FnOnce() -> Result<T, String> + Send,
) -> Result<T, String> {
    FORMAT_WORKERS
        .get_or_init(|| {
            rayon::ThreadPoolBuilder::new()
                .thread_name(|index| format!("sqlbuild-format-{index}"))
                .stack_size(FORMAT_WORKER_STACK_BYTES)
                .build()
                .map_err(|error| error.to_string())
        })
        .as_ref()
        .map_err(Clone::clone)?
        .install(operation)
}

/// Every header rule violation of `text`.
pub(crate) fn lint_header_text(
    text: &str,
    config: HeaderRulesConfig,
) -> Result<Vec<HeaderViolation>, String> {
    let characters: Vec<char> = text.chars().collect();
    header_violations(&characters, &scan_headers(&characters, false), config)
}

/// The header-parse faults among `violations`.
pub(crate) fn parse_faults(violations: &[HeaderViolation]) -> Vec<HeaderViolation> {
    violations
        .iter()
        .filter(|violation| violation.code == RULE_HEADER_PARSE)
        .cloned()
        .collect()
}

/// `text` with header formatting fixes applied, and the faults relocation reported.
pub(crate) fn format_header_text(
    text: &str,
    config: HeaderRulesConfig,
) -> Result<(String, Vec<HeaderViolation>), String> {
    let characters: Vec<char> = text.chars().collect();
    let (formatted, faults) = format_headers(&characters, config, &NativeHeaderParser)?;
    Ok((formatted.into_iter().collect(), faults))
}

/// `operation` over every item on the worker threads; results and the first error keep item order.
pub(crate) fn each_file<T: Sync, R: Send>(
    items: &[T],
    operation: impl Fn(&T) -> Result<R, String> + Sync + Send,
) -> Result<Vec<R>, String> {
    let results: Vec<Result<R, String>> = items.par_iter().map(operation).collect();
    results.into_iter().collect()
}
