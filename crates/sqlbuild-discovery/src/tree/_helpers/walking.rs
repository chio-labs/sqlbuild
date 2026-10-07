//! The parallel walk below one root, listing each directory once per snapshot.

use crate::models::StageDeferral;
use crate::tree::_helpers::listing::{join_relative, list_directory};
use crate::tree::models::{ProjectTree, TreeEntry};
use rayon::iter::{IntoParallelIterator, ParallelIterator};
use std::sync::Arc;

pub(crate) type WalkedDirectory = (String, Arc<Vec<TreeEntry>>);

/// Every directory below `directory`, with its listing, descending only into real directories.
pub(crate) fn walk(
    tree: &ProjectTree,
    directory: &str,
) -> Result<Vec<WalkedDirectory>, StageDeferral> {
    let listing: Arc<Vec<TreeEntry>> = listing(tree, directory)?;
    let children: Vec<String> = listing
        .iter()
        .filter(|entry| entry.is_walkable_dir)
        .map(|entry| join_relative(directory, &entry.name))
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
) -> Result<Arc<Vec<TreeEntry>>, StageDeferral> {
    if let Some(cached) = cached_listing(tree, directory) {
        return Ok(cached);
    }
    let listing: Arc<Vec<TreeEntry>> = Arc::new(list_directory(&tree.absolute(directory))?);
    if let Ok(mut listings) = tree.listings.lock() {
        listings.insert(directory.to_owned(), Arc::clone(&listing));
    }
    Ok(listing)
}

fn cached_listing(tree: &ProjectTree, directory: &str) -> Option<Arc<Vec<TreeEntry>>> {
    match tree.listings.lock() {
        Ok(listings) => listings.get(directory).cloned(),
        Err(_poisoned) => None,
    }
}
