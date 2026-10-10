pub const SQL_WILDCARD: &str = "*";
pub const TIMESTAMP_TYPE: &str = "TIMESTAMP";
pub const OPEN_PAREN: &str = "(";
pub const CLOSE_PAREN: &str = ")";
/// The error text every caught native panic carries across the boundary.
pub const PANIC_MESSAGE: &str = "NativeCompilerError: native SQL compilation panicked";
/// The prefix every native internal failure carries, so the boundary raises `NativeCompilerError`.
pub const NATIVE_FAILURE_PREFIX: &str = "NativeCompilerError: ";
/// The prefix of a native failure Python raised as `ValueError`, with the rest as its message.
pub const PYTHON_VALUE_ERROR: &str = "ValueError: ";
