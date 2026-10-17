//! A model's name: Python's `Path.stem` of its `/`-separated relative path.

/// Python's `PurePath(relative_path).stem` for a `/`-separated relative path.
#[must_use]
pub fn model_file_stem(relative_path: &str) -> &str {
    let name: &str = relative_path
        .rsplit_once('/')
        .map_or(relative_path, |(_, name)| name);
    match name.rfind('.') {
        Some(index) if index > 0 && index + 1 < name.len() => &name[..index],
        _ => name,
    }
}
