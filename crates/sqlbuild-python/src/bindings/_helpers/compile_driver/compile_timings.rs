//! The active compile timing collector of the current thread, as a context variable held it.

use std::cell::RefCell;
use std::rc::Rc;
use std::time::Instant;

use pyo3::prelude::{PyAnyMethods, PyResult, Python};
use sqlbuild_core::compile_timings::main::compile_timing_milliseconds::compile_timing_milliseconds;
use sqlbuild_core::compile_timings::models::CompileTimings;

use crate::bindings::_helpers::compile_driver::python_calls::imported;

/// One compile invocation's collector, shared by every recorder on its thread.
pub(crate) type CompileTimingsHandle = Rc<RefCell<CompileTimings>>;

thread_local! {
    static ACTIVE: RefCell<Option<CompileTimingsHandle>> = const { RefCell::new(None) };
}

/// Run `body` with a fresh collector active on this thread, restoring the previous one after.
pub(crate) fn collect_compile_timings<T>(
    body: impl FnOnce(&CompileTimingsHandle) -> PyResult<T>,
) -> PyResult<T> {
    let collector: CompileTimingsHandle = Rc::default();
    let previous: Option<CompileTimingsHandle> =
        ACTIVE.with(|active| active.replace(Some(Rc::clone(&collector))));
    let result: PyResult<T> = body(&collector);
    ACTIVE.with(|active| active.replace(previous));
    result
}

/// Every reported phase in milliseconds, then every metric.
pub(crate) fn timing_milliseconds(collector: &CompileTimingsHandle) -> Vec<(&'static str, u64)> {
    compile_timing_milliseconds(&collector.borrow())
}

/// Add elapsed nanoseconds to a phase when a collector is active.
pub(crate) fn add_compile_timing(phase: &str, elapsed_ns: u64) {
    if let Some(collector) = active() {
        *collector
            .borrow_mut()
            .elapsed_ns
            .entry(phase.to_owned())
            .or_default() += elapsed_ns;
    }
}

/// Add a non-negative metric value when a collector is active.
pub(crate) fn record_compile_metric(metric: &str, value: i64) {
    if let Some(collector) = active() {
        *collector
            .borrow_mut()
            .metrics
            .entry(metric.to_owned())
            .or_default() += u64::try_from(value).unwrap_or(0);
    }
}

/// Record the wall time `body` spans under `phase` when a collector is active.
pub(crate) fn record_compile_timing<T>(
    phase: &str,
    body: impl FnOnce() -> PyResult<T>,
) -> PyResult<T> {
    if active().is_none() {
        return body();
    }
    let started: Instant = Instant::now();
    let result: PyResult<T> = body();
    add_compile_timing(
        phase,
        u64::try_from(started.elapsed().as_nanos()).unwrap_or(u64::MAX),
    );
    result
}

/// Record the process CPU time `body` spans, including its worker threads, under `phase`.
pub(crate) fn record_compile_cpu_timing<T>(
    py: Python<'_>,
    phase: &str,
    body: impl FnOnce() -> PyResult<T>,
) -> PyResult<T> {
    if active().is_none() {
        return body();
    }
    let started: u64 = process_time_ns(py)?;
    let result: PyResult<T> = body();
    let ended: u64 = process_time_ns(py)?;
    add_compile_timing(phase, ended.saturating_sub(started));
    result
}

fn process_time_ns(py: Python<'_>) -> PyResult<u64> {
    imported(py, "time", "process_time_ns")?.call0()?.extract()
}

fn active() -> Option<CompileTimingsHandle> {
    ACTIVE.with(|active| active.borrow().clone())
}
