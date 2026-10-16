//! Every file and directory under a project, as `os.walk` finds them without following links.

use std::path::{Path, PathBuf};

use crate::project_tree::_helpers::entries::{kind, listed_directory, posix_child};
use crate::project_tree::models::{EntryKind, ProjectTreeEntry};

/// Files and directories under `root`, without links, hidden or top-level tooling directories.
#[must_use]
pub fn project_tree_entries(root: &Path) -> Vec<ProjectTreeEntry> {
    let mut entries: Vec<ProjectTreeEntry> = Vec::new();
    let mut pending: Vec<PathBuf> = vec![PathBuf::new()];
    while let Some(relative) = pending.pop() {
        let Ok(listing) = std::fs::read_dir(root.join(&relative)) else {
            continue;
        };
        for entry in listing.flatten() {
            let child: PathBuf = posix_child(&relative, &entry.file_name());
            match kind(&entry) {
                EntryKind::Link => {}
                EntryKind::Directory => {
                    if listed_directory(&entry, relative.as_os_str().is_empty()) {
                        entries.push(ProjectTreeEntry {
                            relative: child.clone(),
                            is_file: false,
                        });
                        pending.push(child);
                    }
                }
                EntryKind::Other => entries.push(ProjectTreeEntry {
                    relative: child,
                    is_file: true,
                }),
            }
        }
    }
    entries
}
