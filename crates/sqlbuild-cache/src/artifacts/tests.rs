#[path = "tests/helpers.rs"]
mod helpers;
#[cfg(unix)]
#[path = "tests/test_remove_stale.rs"]
mod remove_stale;
#[path = "tests/test_reusable_record.rs"]
mod reusable_record;
#[path = "tests/test_types.rs"]
mod test_types;
#[path = "tests/test_write_artifacts.rs"]
mod write_artifacts;
