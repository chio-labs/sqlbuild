#[path = "tests/helpers.rs"]
mod helpers;
#[path = "tests/test_ordering.rs"]
mod ordering;
#[path = "tests/test_os_failures.rs"]
mod os_failures;
#[path = "tests/test_project_tree.rs"]
mod project_tree;
#[path = "tests/test_raw_segments.rs"]
mod raw_segments;
#[path = "tests/test_types.rs"]
mod test_types;
#[cfg(unix)]
#[path = "tests/test_undecodable_names.rs"]
mod undecodable_names;
#[cfg(windows)]
#[path = "tests/test_windows_junctions.rs"]
mod windows_junctions;
