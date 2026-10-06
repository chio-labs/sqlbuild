//! Convert unwinding native failures into ordinary named compiler errors.

use std::panic::{AssertUnwindSafe, catch_unwind};

/// The error text every caught native panic carries across the boundary.
pub const PANIC_MESSAGE: &str = "NativeCompilerError: native SQL compilation panicked";

pub fn catch_compiler_panic<T>(operation: impl FnOnce() -> Result<T, String>) -> Result<T, String> {
    match catch_unwind(AssertUnwindSafe(operation)) {
        Ok(result) => result,
        Err(_) => Err(PANIC_MESSAGE.to_owned()),
    }
}

pub fn is_compiler_panic(message: &str) -> bool {
    message == PANIC_MESSAGE
}
