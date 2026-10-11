//! `sqb`: the native SQLBuild command line.

use std::process::ExitCode;

use sqlbuild_cli::launcher::main::run_launcher::run_launcher;

fn main() -> ExitCode {
    run_launcher()
}
