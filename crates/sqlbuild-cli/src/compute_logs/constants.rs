//! Compute log format version, retention defaults and storage file names.

pub const COMPUTE_LOG_FORMAT_VERSION: i64 = 1;
pub const DEFAULT_RETENTION_COUNT: usize = 20;
pub const METADATA_FILE_NAME: &str = "metadata.json";
pub const COMPLETE_FILE_NAME: &str = "complete";
pub const PRUNE_LOCK_FILE_NAME: &str = ".prune.lock";
pub const STDOUT_FILE_NAME: &str = "stdout.log";
pub const STDERR_FILE_NAME: &str = "stderr.log";
pub const DIAGNOSTICS_FILE_NAME: &str = "diagnostics.jsonl";
/// Stream files in the order Python creates them.
pub const STREAM_FILE_NAMES: [&str; 3] =
    [STDOUT_FILE_NAME, STDERR_FILE_NAME, DIAGNOSTICS_FILE_NAME];
pub const MICROSECONDS_PER_SECOND: i64 = 1_000_000;
pub const SECONDS_PER_DAY: i64 = 86_400;
pub const SECONDS_PER_HOUR: i64 = 3_600;
pub const SECONDS_PER_MINUTE: i64 = 60;
pub const MICROSECOND_DIGITS: usize = 6;
/// Days in a 400-year Gregorian era.
pub const DAYS_PER_ERA: i64 = 146_097;
pub const YEARS_PER_ERA: i64 = 400;
pub const FEBRUARY: i64 = 2;
/// January's index when months count from March, as the civil date algorithm does.
pub const MARCH_BASED_JANUARY: i64 = 10;
/// Days from 0000-03-01 to 1970-01-01.
pub const EPOCH_DAY_OFFSET: i64 = 719_468;
/// `YYYY-MM-DD`: the length of a capture date directory name and its hyphen positions.
pub const CAPTURE_DATE_LENGTH: usize = 10;
pub const CAPTURE_DATE_HYPHENS: [usize; 2] = [4, 7];
pub const MAX_READ_BYTES: u64 = 1_048_576;
pub const MAX_CAPTURE_ID_LENGTH: usize = 128;
pub const DEFAULT_LOG_DIRECTORY: &str = "logs";
pub const MONTHS_PER_YEAR: i64 = 12;
pub const MAX_DAY_OF_MONTH: i64 = 31;
pub const HOURS_PER_DAY: i64 = 24;
