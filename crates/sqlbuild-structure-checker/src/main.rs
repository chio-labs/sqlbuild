//! Command adapter for the structure checker.

use std::process::ExitCode;

use fensu_structure_checker::command::main::run_checker::run_checker;

fn main() -> ExitCode {
    run_checker()
}
