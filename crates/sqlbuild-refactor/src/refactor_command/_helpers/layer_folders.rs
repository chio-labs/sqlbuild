//! Layer folders read from model names and paths, as the layer-folder rules read them.

use crate::refactor_command::constants::{
    CONTIGUOUS_LAYER_FOLDERS, CURRENT_DIRECTORY, LAYER_FOLDERS, MODEL_NAME_LAYER_INDEX,
    MODEL_NAME_LAYER_SEPARATOR, MODEL_NAME_PART_COUNTS,
};

pub(crate) fn folder_of(
    folders: &[(&str, &'static [&'static str])],
    layer: &str,
) -> Option<&'static [&'static str]> {
    folders
        .iter()
        .find(|(name, _)| *name == layer)
        .map(|(_, folder)| *folder)
}

/// The layer segment of a name in the rule grammar, as the layer-folder rules read it.
pub(crate) fn name_layer(name: &str) -> Option<&str> {
    let parts: Vec<&str> = name.split(MODEL_NAME_LAYER_SEPARATOR).collect();
    if MODEL_NAME_PART_COUNTS.contains(&parts.len()) {
        return Some(parts[MODEL_NAME_LAYER_INDEX]);
    }
    None
}

/// `PurePosixPath(path).parts`.
pub(crate) fn path_parts(path: &str) -> Vec<&str> {
    let mut parts: Vec<&str> = Vec::new();
    if path.starts_with('/') {
        parts.push("/");
    }
    parts.extend(
        path.split('/')
            .filter(|part| !part.is_empty() && *part != CURRENT_DIRECTORY),
    );
    parts
}

/// Swap the current layer's own folder for the new one, keeping the folders around it.
pub(crate) fn mirrored_folder(
    original_path: &str,
    current_layer: Option<&str>,
    layer_folder: &[&str],
) -> Option<(Vec<String>, Vec<String>)> {
    let current_layer: &str = current_layer.unwrap_or_default();
    let candidates: Vec<&[&str]> = [
        folder_of(&LAYER_FOLDERS, current_layer),
        folder_of(&CONTIGUOUS_LAYER_FOLDERS, current_layer),
    ]
    .into_iter()
    .flatten()
    .collect();
    let mut parent: Vec<&str> = path_parts(original_path);
    parent.pop();
    for current in candidates {
        for start in 1..parent.len() {
            let end: usize = (start + current.len()).min(parent.len());
            if parent[start..end] == *current {
                let head: Vec<String> = parent[..start]
                    .iter()
                    .chain(layer_folder)
                    .map(|part| (*part).to_owned())
                    .collect();
                let tail: Vec<String> = parent[end..]
                    .iter()
                    .map(|part| (*part).to_owned())
                    .collect();
                return Some((head, tail));
            }
        }
    }
    None
}
