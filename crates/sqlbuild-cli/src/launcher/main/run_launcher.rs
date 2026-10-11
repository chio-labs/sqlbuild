//! The `sqb` and `sqlbuild` executables' whole process.

use std::ffi::OsString;
use std::process::ExitCode;
use std::time::{Instant, SystemTime};

use crate::launcher::_helpers::dispatch::launch;

/// Run this process's invocation; an exit code beyond one byte ends the process directly.
pub fn run_launcher() -> ExitCode {
    let started = (Instant::now(), SystemTime::now());
    let arguments: Vec<OsString> = std::env::args_os().skip(1).collect();
    let code: i32 = launch(arguments, started);
    match u8::try_from(code) {
        Ok(code) => ExitCode::from(code),
        Err(_) => std::process::exit(code),
    }
}
