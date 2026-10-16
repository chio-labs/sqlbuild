/// The mode new artifacts are created with before the process umask, as Python's `os.open`.
pub const NEW_FILE_MODE: u32 = 0o666;
/// The extension every compiled SQL test artifact carries.
pub(crate) const SQL_EXTENSION: &str = "sql";
#[cfg(unix)]
pub(crate) const NANOS_PER_SECOND: i64 = 1_000_000_000;
