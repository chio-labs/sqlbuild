//! Convert unwinding native failures into ordinary named compiler errors.

use crate::constants::PANIC_MESSAGE;
use std::panic::{AssertUnwindSafe, catch_unwind};

pub fn catch_compiler_panic<T>(operation: impl FnOnce() -> Result<T, String>) -> Result<T, String> {
    match catch_unwind(AssertUnwindSafe(operation)) {
        Ok(result) => result,
        Err(_) => Err(PANIC_MESSAGE.to_owned()),
    }
}
