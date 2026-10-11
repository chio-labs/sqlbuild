//! `PurePosixPath` parts, parents, names and common prefixes of project-relative paths.

const SEPARATOR: char = '/';
const ROOT: &str = "/";
const CURRENT: &str = ".";

/// `PurePosixPath(path).parts`: empty and `.` components dropped, a leading `/` kept.
pub(crate) fn parts(path: &str) -> Vec<&str> {
    let mut parts: Vec<&str> = Vec::new();
    if path.starts_with(SEPARATOR) {
        parts.push(ROOT);
    }
    parts.extend(
        path.split(SEPARATOR)
            .filter(|part| !part.is_empty() && *part != CURRENT),
    );
    parts
}

/// `PurePosixPath(*parts).as_posix()`.
pub(crate) fn joined(parts: &[&str]) -> String {
    match parts.split_first() {
        None => CURRENT.to_owned(),
        Some((&ROOT, rest)) => format!("{ROOT}{}", rest.join(ROOT)),
        Some(_) => parts.join(ROOT),
    }
}

/// `PurePosixPath(path).parent.as_posix()`.
pub(crate) fn parent(path: &str) -> String {
    let parts: Vec<&str> = parts(path);
    match parts.as_slice() {
        [] => CURRENT.to_owned(),
        [ROOT] => ROOT.to_owned(),
        [.., _] => joined(&parts[..parts.len() - 1]),
    }
}

/// `PurePosixPath(path).name`.
pub(crate) fn name(path: &str) -> &str {
    match parts(path).last() {
        Some(&ROOT) | None => "",
        Some(last) => last,
    }
}

/// The longest common leading parts of `paths`, as `_lca` joins them.
pub(crate) fn common_prefix(paths: &[&str]) -> String {
    let split: Vec<Vec<&str>> = paths.iter().map(|path| parts(path)).collect();
    let shortest: usize = split.iter().map(Vec::len).min().unwrap_or(0);
    let mut common: Vec<&str> = Vec::new();
    for position in 0..shortest {
        let component: &str = split[0][position];
        if split.iter().any(|item| item[position] != component) {
            break;
        }
        common.push(component);
    }
    joined(&common)
}
