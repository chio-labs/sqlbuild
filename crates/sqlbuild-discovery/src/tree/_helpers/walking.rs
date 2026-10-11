//! The parallel walk below one root, listing each directory once per snapshot.

use crate::models::StageFailure;
use crate::tree::_helpers::listing::{join_relative, list_directory};
use crate::tree::models::{ProjectTree, TreeEntry};
use rayon::iter::{IntoParallelIterator, ParallelIterator};
use std::ffi::OsString;
use std::sync::{Arc, PoisonError};

pub(crate) type WalkedDirectory = (String, Arc<Vec<TreeEntry>>);

/// Every directory below `directory`, with its listing, descending only into real directories.
pub(crate) fn walk(
    tree: &ProjectTree,
    directory: &str,
) -> Result<Vec<WalkedDirectory>, StageFailure> {
    let listing: Arc<Vec<TreeEntry>> = listing(tree, directory)?;
    let children: Vec<String> = listing
        .iter()
        .filter(|entry| entry.is_walkable_dir)
        .map(|entry| join_relative(directory, &entry.segment))
        .collect();
    let nested: Vec<Vec<WalkedDirectory>> = children
        .into_par_iter()
        .map(|child| walk(tree, &child))
        .collect::<Result<_, _>>()?;
    let mut walked: Vec<WalkedDirectory> = vec![(directory.to_owned(), listing)];
    walked.extend(nested.into_iter().flatten());
    Ok(walked)
}

pub(crate) fn listing(
    tree: &ProjectTree,
    directory: &str,
) -> Result<Arc<Vec<TreeEntry>>, StageFailure> {
    if let Some(cached) = cached_listing(tree, directory) {
        return Ok(cached);
    }
    let read = list_directory(&tree.absolute(directory));
    if read.interrupted {
        tree.interrupted
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .push(directory.to_owned());
    }
    let listing: Arc<Vec<TreeEntry>> = Arc::new(read.entries);
    remember_raw_names(tree, directory, &listing);
    if let Ok(mut listings) = tree.listings.lock() {
        listings.insert(directory.to_owned(), Arc::clone(&listing));
    }
    Ok(listing)
}

fn remember_raw_names(tree: &ProjectTree, directory: &str, listing: &[TreeEntry]) {
    let mut undecodable: Vec<(String, OsString)> = Vec::new();
    for entry in listing {
        if let Some(raw) = &entry.raw_name {
            undecodable.push((join_relative(directory, &entry.segment), raw.clone()));
        }
    }
    if !undecodable.is_empty()
        && let Ok(mut raw_names) = tree.raw_names.write()
    {
        raw_names.extend(undecodable);
    }
}

fn cached_listing(tree: &ProjectTree, directory: &str) -> Option<Arc<Vec<TreeEntry>>> {
    match tree.listings.lock() {
        Ok(listings) => listings.get(directory).cloned(),
        Err(_poisoned) => None,
    }
}
