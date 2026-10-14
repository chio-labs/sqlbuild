//! The project name derived from its directory.

/// The directory name with dashes and spaces as underscores, lowercased.
#[must_use]
pub fn init_project_name(directory_name: &str) -> String {
    directory_name.replace(['-', ' '], "_").to_lowercase()
}
