//! The stamp of a compiled tree that held exactly its managed files when last cleaned.

use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::digest::main::content_digest::content_digest;
use crate::digest::types::ContentDigest;
use crate::store::main::open_native_store::open_native_store;
use crate::store::models::{NativeStore, RecordReader, RecordWriter};

const STORE_KIND: &str = "compiled-tree";
const STORE_ENVIRONMENT: &str = "compiled-tree-1";

/// One folder's identity: its path, inode, and modification and change times.
#[derive(Clone, Debug, PartialEq, Eq)]
struct FolderStamp {
    path: String,
    inode: u64,
    mtime_ns: i64,
    ctime_ns: i64,
}

fn entry_key() -> ContentDigest {
    content_digest(&["tree"])
}

/// The digest of the compiled folder and its managed file set, in any order.
pub(crate) fn managed_digest(compiled_dir: &Path, managed: &HashSet<PathBuf>) -> ContentDigest {
    let mut paths: Vec<String> = managed
        .iter()
        .map(|path| path.to_string_lossy().into_owned())
        .collect();
    paths.sort_unstable();
    let mut hasher: blake3::Hasher = blake3::Hasher::new();
    for part in std::iter::once(compiled_dir.to_string_lossy().into_owned()).chain(paths) {
        let _ = hasher.update(&(part.len() as u64).to_le_bytes());
        let _ = hasher.update(part.as_bytes());
    }
    *hasher.finalize().as_bytes()
}

#[cfg(unix)]
fn folder_stamp(path: &Path) -> Option<FolderStamp> {
    use std::os::unix::fs::MetadataExt;

    let metadata: std::fs::Metadata = match std::fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(_absent) => return None,
    };
    if !metadata.is_dir() {
        return None;
    }
    Some(FolderStamp {
        path: path.to_string_lossy().into_owned(),
        inode: metadata.ino(),
        mtime_ns: metadata.mtime() * 1_000_000_000 + metadata.mtime_nsec(),
        ctime_ns: metadata.ctime() * 1_000_000_000 + metadata.ctime_nsec(),
    })
}

#[cfg(not(unix))]
fn folder_stamp(_path: &Path) -> Option<FolderStamp> {
    None
}

/// Whether the tree recorded at `stamp_path` for `digest` is unchanged on disk.
pub(crate) fn tree_unchanged(stamp_path: &Path, digest: &ContentDigest) -> bool {
    let Ok(mut store) = open_native_store(stamp_path, STORE_KIND, STORE_ENVIRONMENT) else {
        return false;
    };
    let Some(bytes) = store.get(&entry_key()) else {
        return false;
    };
    let Ok((recorded, folders)) = decode(bytes) else {
        return false;
    };
    recorded == *digest
        && !folders.is_empty()
        && folders
            .iter()
            .all(|folder| folder_stamp(Path::new(&folder.path)).as_ref() == Some(folder))
}

/// Remove the recorded stamp, before the tree is changed.
pub(crate) fn forget_tree(stamp_path: &Path) {
    let _ = std::fs::remove_file(stamp_path);
}

/// The current time in nanoseconds since the epoch, as file stamps record it.
pub(crate) fn now_ns() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |elapsed| {
            i64::try_from(elapsed.as_nanos()).unwrap_or(i64::MAX)
        })
}

/// Record `folders` as the tree `digest` names when each stamps and changed before `trusted_ns`.
pub(crate) fn record_tree(
    stamp_path: &Path,
    digest: &ContentDigest,
    folders: &[PathBuf],
    trusted_ns: i64,
) {
    let Some(stamps) = folders
        .iter()
        .map(|path| folder_stamp(path))
        .collect::<Option<Vec<FolderStamp>>>()
    else {
        return;
    };
    let settled: bool = !stamps.is_empty()
        && stamps
            .iter()
            .all(|stamp| stamp.mtime_ns.max(stamp.ctime_ns) < trusted_ns);
    if !settled {
        return;
    }
    let mut store: NativeStore = NativeStore {
        kind: STORE_KIND.to_owned(),
        environment: STORE_ENVIRONMENT.to_owned(),
        ..NativeStore::default()
    };
    store.put(entry_key(), encode(digest, &stamps));
    let _ = store.save(stamp_path, &[]);
}

fn encode(digest: &ContentDigest, folders: &[FolderStamp]) -> Vec<u8> {
    let mut writer: RecordWriter = RecordWriter::default();
    writer.put_bytes(digest);
    writer.put_u64(folders.len() as u64);
    for folder in folders {
        writer.put_str(&folder.path);
        writer.put_u64(folder.inode);
        writer.put_u64(folder.mtime_ns as u64);
        writer.put_u64(folder.ctime_ns as u64);
    }
    writer.into_bytes()
}

fn decode(
    bytes: &[u8],
) -> Result<(ContentDigest, Vec<FolderStamp>), crate::store::errors::StoreDecodeError> {
    let mut reader: RecordReader<'_> = RecordReader::new(bytes);
    let digest: ContentDigest = reader
        .bytes()?
        .try_into()
        .map_err(|_| crate::store::errors::StoreDecodeError)?;
    let count: u64 = reader.u64()?;
    let mut folders: Vec<FolderStamp> = Vec::new();
    for _ in 0..count {
        folders.push(FolderStamp {
            path: reader.string()?,
            inode: reader.u64()?,
            mtime_ns: reader.u64()? as i64,
            ctime_ns: reader.u64()? as i64,
        });
    }
    reader.finish()?;
    Ok((digest, folders))
}
