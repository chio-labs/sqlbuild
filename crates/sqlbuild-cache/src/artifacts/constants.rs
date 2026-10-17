/// The mode new artifacts are created with before the process umask, as Python's `os.open`.
pub const NEW_FILE_MODE: u32 = 0o666;
/// The extension every compiled SQL test artifact carries.
pub(crate) const SQL_EXTENSION: &str = "sql";
#[cfg(unix)]
pub(crate) const NANOS_PER_SECOND: i64 = 1_000_000_000;
/// Below this many files a sequential write is cheaper than starting a pool.
pub(crate) const PARALLEL_WRITE_MIN_FILES: usize = 64;
/// Writer threads for one artifact batch, matching SQL test planning's fixed pool.
pub(crate) const WRITE_WORKERS: usize = 4;
