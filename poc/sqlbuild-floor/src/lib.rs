//! Throwaway proof of concept: shared helpers for the compile-floor benchmarks. Not for merge.

use std::time::Instant;

/// Process CPU seconds (user + system, all threads) from `/proc/self/stat`.
pub fn process_cpu_seconds() -> f64 {
    let stat = std::fs::read_to_string("/proc/self/stat").unwrap_or_default();
    let after = stat.rsplit_once(')').map_or("", |(_, rest)| rest);
    let fields: Vec<&str> = after.split_whitespace().collect();
    let ticks = |index: usize| {
        fields
            .get(index)
            .and_then(|v| v.parse::<f64>().ok())
            .unwrap_or(0.0)
    };
    // Fields after the command name start at "state" (field 3); utime is 14, stime 15.
    (ticks(11) + ticks(12)) / 100.0
}

/// Thread CPU seconds of the calling thread from `/proc/thread-self/stat`.
pub fn thread_cpu_seconds() -> f64 {
    let stat = std::fs::read_to_string("/proc/thread-self/stat").unwrap_or_default();
    let after = stat.rsplit_once(')').map_or("", |(_, rest)| rest);
    let fields: Vec<&str> = after.split_whitespace().collect();
    let ticks = |index: usize| {
        fields
            .get(index)
            .and_then(|v| v.parse::<f64>().ok())
            .unwrap_or(0.0)
    };
    (ticks(11) + ticks(12)) / 100.0
}

pub fn load_average() -> f64 {
    std::fs::read_to_string("/proc/loadavg")
        .ok()
        .and_then(|text| text.split_whitespace().next().and_then(|v| v.parse().ok()))
        .unwrap_or(f64::NAN)
}

/// Wall seconds and process CPU seconds of `work`.
pub fn measure<T>(work: impl FnOnce() -> T) -> (T, f64, f64) {
    let cpu = process_cpu_seconds();
    let start = Instant::now();
    let value = work();
    (
        value,
        start.elapsed().as_secs_f64(),
        process_cpu_seconds() - cpu,
    )
}

pub fn median(values: &mut [f64]) -> f64 {
    if values.is_empty() {
        return f64::NAN;
    }
    values.sort_by(f64::total_cmp);
    let middle = values.len() / 2;
    if values.len() % 2 == 1 {
        values[middle]
    } else {
        (values[middle - 1] + values[middle]) / 2.0
    }
}

pub fn pool(threads: usize) -> rayon::ThreadPool {
    rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .stack_size(16 * 1024 * 1024)
        .build()
        .expect("thread pool")
}

pub mod pylit;
pub mod scan;
