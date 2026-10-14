//! The launch record format shared with `sqlbuild.cli.entry.launch_records`.

/// Bumped whenever the launch record changes shape; older records are ignored.
pub const LAUNCH_RECORD_FORMAT: i64 = 1;
/// Launch records live under `<project>/target/cache/<this>/<key>.json`.
pub const LAUNCH_RECORD_DIRECTORY: [&str; 3] = ["target", "cache", "launcher-v1"];
pub const LAUNCH_RECORD_SUFFIX: &str = ".json";
pub const OUTPUT_FAILURE_EXIT_CODE: i64 = 1;
/// How many launch records one project keeps; older ones are pruned after each write.
pub const LAUNCH_RECORD_LIMIT: usize = 32;
