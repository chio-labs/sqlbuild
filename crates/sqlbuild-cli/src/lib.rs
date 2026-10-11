//! The native `sqb` executable: replays reused compiles and hands other invocations to Python.

#![forbid(unsafe_code)]

pub mod compute_logs;
pub mod launcher;
pub mod replay;
