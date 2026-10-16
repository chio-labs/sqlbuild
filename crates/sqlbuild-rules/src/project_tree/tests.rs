#[cfg(unix)]
#[path = "tests/test_escapes.rs"]
mod escapes;
#[cfg(unix)]
#[path = "tests/helpers.rs"]
mod helpers;
#[path = "tests/test_path_queries.rs"]
mod path_queries;
#[cfg(unix)]
#[path = "tests/test_project_tree.rs"]
mod project_tree;
#[cfg(unix)]
#[path = "tests/test_relative_parts.rs"]
mod relative_parts;
#[path = "tests/test_types.rs"]
mod test_types;
