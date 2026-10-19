//! The project image beside a slot: the facts a delta compile patches, kept for recent slots only.

use std::path::{Path, PathBuf};
use std::time::SystemTime;

use crate::digest::types::ContentDigest;
use crate::project_reuse::_helpers::sections::{
    decode_sections, encode_sections, write_atomically,
};
use crate::project_reuse::constants::{
    REUSE_IMAGE_SUFFIX, REUSE_OUTPUT_SUFFIX, REUSE_STORE_SUFFIX,
};
use crate::project_reuse::types::ImageSections;

const IMAGE_ROLE: &str = "project-reuse-image";

/// The image file paired with the slot file at `path`.
pub(crate) fn image_path(path: &Path) -> PathBuf {
    path.with_extension(REUSE_IMAGE_SUFFIX)
}

/// Write `sections` as the slot's image; returns the identity the slot names it by.
pub(crate) fn write_image(path: &Path, sections: &ImageSections) -> std::io::Result<ContentDigest> {
    let borrowed: Vec<(&str, &[u8])> = sections
        .iter()
        .map(|(name, bytes)| (name.as_str(), bytes.as_slice()))
        .collect();
    let (encoded, identity) = encode_sections(IMAGE_ROLE, &borrowed);
    write_atomically(&image_path(path), &encoded)?;
    Ok(identity)
}

/// The slot's image, marked as used, or `None` when it is missing, damaged or another compile's.
pub(crate) fn read_image(path: &Path, identity: &ContentDigest) -> Option<ImageSections> {
    let file_path: PathBuf = image_path(path);
    let bytes: Vec<u8> = match std::fs::read(&file_path) {
        Ok(bytes) => bytes,
        Err(_unreadable) => return None,
    };
    let Ok(file) = decode_sections(&bytes, IMAGE_ROLE) else {
        return None;
    };
    if file.identity != *identity {
        return None;
    }
    let sections: ImageSections = file
        .sections
        .into_iter()
        .map(|(name, bytes)| (name, bytes.to_vec()))
        .collect();
    mark_used(&file_path);
    Some(sections)
}

/// Mark an image as just used; failing to is harmless and only affects pruning order.
pub(crate) fn mark_used(path: &Path) {
    if let Ok(file) = std::fs::OpenOptions::new().append(true).open(path) {
        let _ = file.set_modified(SystemTime::now());
    }
}

/// Keep the images of the `keep_images` most recently used slots, and drop images no slot names.
pub(crate) fn prune_images(directory: &Path, keep: &Path, keep_images: usize) {
    let Ok(entries) = std::fs::read_dir(directory) else {
        return;
    };
    let keep_image: PathBuf = image_path(keep);
    let mut images: Vec<(SystemTime, PathBuf)> = Vec::new();
    for path in entries.flatten().map(|entry| entry.path()) {
        if !path
            .extension()
            .is_some_and(|suffix| suffix == REUSE_IMAGE_SUFFIX)
        {
            continue;
        }
        let slot: PathBuf = path.with_extension(REUSE_STORE_SUFFIX);
        let output: PathBuf = path.with_extension(REUSE_OUTPUT_SUFFIX);
        if !slot.exists() && !output.exists() {
            let _ = std::fs::remove_file(&path);
            continue;
        }
        if path == keep_image {
            continue;
        }
        let Ok(modified) = std::fs::metadata(&path).and_then(|metadata| metadata.modified()) else {
            continue;
        };
        images.push((modified, path));
    }
    images.sort_by(|left, right| right.cmp(left));
    for (_, stale) in images.into_iter().skip(keep_images.saturating_sub(1)) {
        let _ = std::fs::remove_file(stale);
    }
}
