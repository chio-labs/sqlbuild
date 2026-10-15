//! `importlib.metadata` distribution lookup over search paths, for code identity facts.

use std::io::ErrorKind;
use std::path::{Path, PathBuf};

use crate::digest::constants::{METADATA_DIRECTORY_SUFFIXES, METADATA_FILES};

/// The first metadata folder of `name` along `search_paths`, as `importlib.metadata` finds it.
pub(crate) fn distribution_directory(search_paths: &[PathBuf], name: &str) -> Option<PathBuf> {
    let wanted: String = normalized(name);
    for root in search_paths {
        let directory: &Path = if root.as_os_str().is_empty() {
            Path::new(".")
        } else {
            root
        };
        if let Some(child) = children(directory)
            .into_iter()
            .find(|child| metadata_name(child).is_some_and(|found| normalized(&found) == wanted))
        {
            return Some(root.join(child));
        }
    }
    None
}

/// The `Version` header of a distribution's metadata, when it has one.
pub(crate) fn distribution_version(directory: &Path) -> Option<String> {
    for file in METADATA_FILES {
        if let Some(text) = optional_text(&directory.join(file)) {
            return header_value(&text, "version");
        }
    }
    None
}

/// A file's bytes, or `None` where `importlib.metadata` treats the file as absent.
pub(crate) fn optional_bytes(path: &Path) -> Option<Vec<u8>> {
    match std::fs::read(path) {
        Ok(bytes) => Some(bytes),
        Err(error) if absent(&error) => None,
        Err(_) => None,
    }
}

/// Entry names of a search path folder; folders Python cannot list have none.
fn children(directory: &Path) -> Vec<String> {
    let entries: std::fs::ReadDir = match std::fs::read_dir(directory) {
        Ok(entries) => entries,
        Err(error) if absent(&error) => return Vec::new(),
        Err(_) => return Vec::new(),
    };
    let mut names: Vec<String> = Vec::new();
    for entry in entries.flatten() {
        names.push(entry.file_name().to_string_lossy().into_owned());
    }
    names
}

fn optional_text(path: &Path) -> Option<String> {
    optional_bytes(path).map(|bytes| String::from_utf8_lossy(&bytes).into_owned())
}

fn absent(error: &std::io::Error) -> bool {
    matches!(
        error.kind(),
        ErrorKind::NotFound | ErrorKind::NotADirectory | ErrorKind::IsADirectory
    )
}

/// The distribution name a metadata folder entry names, before its version.
fn metadata_name(child: &str) -> Option<String> {
    let lowered: String = child.to_lowercase();
    METADATA_DIRECTORY_SUFFIXES
        .iter()
        .any(|suffix| lowered.ends_with(suffix))
        .then(|| {
            let stem: &str = lowered.rsplit_once('.').map_or("", |(stem, _)| stem);
            stem.split('-').next().unwrap_or_default().to_owned()
        })
}

/// `re.sub(r"[-_.]+", "-", name).lower().replace("-", "_")`.
fn normalized(name: &str) -> String {
    let mut text: String = String::with_capacity(name.len());
    let mut separator: bool = false;
    for character in name.chars() {
        if matches!(character, '-' | '_' | '.') {
            if !separator {
                text.push('_');
            }
            separator = true;
        } else {
            text.extend(character.to_lowercase());
            separator = false;
        }
    }
    text
}

/// The first value of a case-insensitive header in an RFC 822 style header block.
fn header_value(text: &str, name: &str) -> Option<String> {
    let mut value: Option<String> = None;
    for line in text.lines() {
        if line.is_empty() {
            break;
        }
        if line.starts_with([' ', '\t']) {
            if let Some(current) = value.as_mut() {
                current.push_str(line);
            }
            continue;
        }
        if value.is_some() {
            break;
        }
        if let Some((header, rest)) = line.split_once(':')
            && header.eq_ignore_ascii_case(name)
        {
            value = Some(rest.trim_start().to_owned());
        }
    }
    value.map(|text| text.trim_end().to_owned())
}
