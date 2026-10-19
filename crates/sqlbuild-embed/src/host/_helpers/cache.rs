//! The per-user cache of interpreter discovery, keyed by the interpreter's file stamps.

use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

use crate::host::_helpers::installation::venv_config_paths;
use crate::host::constants::{CACHE_FORMAT, CACHED_EMBEDDABLE, CACHED_EXEC};
use crate::host::models::{EmbeddableInterpreter, HostDiscovery, LocatedHost};

fn file_stamp(path: &Path) -> String {
    let Ok(metadata) = std::fs::metadata(path) else {
        return "missing".to_owned();
    };
    let modified: u128 = match metadata
        .modified()
        .map(|time| time.duration_since(UNIX_EPOCH))
    {
        Ok(Ok(elapsed)) => elapsed.as_nanos(),
        _ => 0,
    };
    format!("{}:{modified}", metadata.len())
}

fn single_line(path: &Path) -> Option<&str> {
    path.to_str()
        .filter(|text| !text.contains(['\n', '\r', '\t']))
}

/// The interpreter's identity: its path, resolved file and venv configuration, with their stamps.
pub(crate) fn interpreter_stamp(interpreter: &Path) -> Option<String> {
    let Ok(resolved) = std::fs::canonicalize(interpreter) else {
        return None;
    };
    let mut fields: Vec<String> = vec![
        single_line(interpreter)?.to_owned(),
        single_line(&resolved)?.to_owned(),
        file_stamp(&resolved),
    ];
    fields.extend(
        venv_config_paths(interpreter)
            .iter()
            .map(|path| file_stamp(path)),
    );
    Some(fields.join("\t"))
}

/// The cache file of one interpreter path.
pub(crate) fn cache_file(root: &Path, interpreter: &Path) -> PathBuf {
    let digest = blake3::hash(interpreter.as_os_str().as_encoded_bytes());
    root.join(&digest.to_hex()[..32])
}

/// The watched-file line: the file and its stamp, or empty when nothing is watched.
fn watched_line(watched: Option<&Path>) -> Option<String> {
    match watched {
        Some(path) => Some(format!("{}\t{}", single_line(path)?, file_stamp(path))),
        None => Some(String::new()),
    }
}

/// The cached discovery for `interpreter`, if one was stored for exactly these stamps.
pub(crate) fn read_cached(root: &Path, interpreter: &Path, stamp: &str) -> Option<HostDiscovery> {
    let Ok(text) = std::fs::read_to_string(cache_file(root, interpreter)) else {
        return None;
    };
    let mut lines = text.split('\n');
    if lines.next()? != CACHE_FORMAT || lines.next()? != stamp {
        return None;
    }
    let entry: &str = lines.next()?;
    let watched: &str = lines.next()?;
    let current: String = match watched.split_once('\t') {
        Some((path, _)) => watched_line(Some(Path::new(path)))?,
        None => String::new(),
    };
    if current != watched {
        return None;
    }
    let fields: Vec<&str> = entry.split('\t').collect();
    match fields.as_slice() {
        [CACHED_EMBEDDABLE, library, version] => {
            Some(HostDiscovery::Embeddable(EmbeddableInterpreter {
                interpreter: interpreter.to_path_buf(),
                library: PathBuf::from(library),
                version: (*version).to_owned(),
            }))
        }
        [CACHED_EXEC, reason] => Some(HostDiscovery::Exec((*reason).to_owned())),
        _ => None,
    }
}

fn entry_line(found: &HostDiscovery) -> Option<String> {
    match found {
        HostDiscovery::Embeddable(found) => Some(format!(
            "{CACHED_EMBEDDABLE}\t{}\t{}",
            single_line(&found.library)?,
            found.version
        )),
        HostDiscovery::Exec(reason) => Some(format!(
            "{CACHED_EXEC}\t{}",
            reason.replace(['\n', '\r', '\t'], " ")
        )),
    }
}

/// Store `located` for `interpreter` at `stamp`, replacing the file atomically; failures are ignored.
pub(crate) fn write_cached(root: &Path, interpreter: &Path, stamp: &str, located: &LocatedHost) {
    let (Some(entry), Some(watched)) = (
        entry_line(&located.found),
        watched_line(located.watched.as_deref()),
    ) else {
        return;
    };
    let path: PathBuf = cache_file(root, interpreter);
    let text = format!("{CACHE_FORMAT}\n{stamp}\n{entry}\n{watched}\n");
    let staged: PathBuf = path.with_extension(format!("{}.tmp", std::process::id()));
    let written = std::fs::create_dir_all(root)
        .and_then(|()| std::fs::File::create(&staged))
        .and_then(|mut file| file.write_all(text.as_bytes()))
        .and_then(|()| std::fs::rename(&staged, &path));
    if written.is_err() {
        let _ = std::fs::remove_file(&staged);
    }
}

/// Forget the cached discovery for `interpreter`, after it failed to load.
pub(crate) fn forget_cached(root: &Path, interpreter: &Path) {
    let _ = std::fs::remove_file(cache_file(root, interpreter));
}
