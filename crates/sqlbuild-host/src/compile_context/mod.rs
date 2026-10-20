//! Per-compile host state: the thread's timing collector and the diagnostic sink producers report into.

pub(crate) mod _helpers;
pub mod main;
pub mod types;

#[cfg(test)]
mod tests;
