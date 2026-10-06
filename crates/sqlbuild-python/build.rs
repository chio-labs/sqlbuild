//! Derive a content identity for this native build so local caches notice source changes.
//!
//! The identity hashes every file under the listed crate entries plus the workspace lockfile,
//! keyed by `/`-separated paths relative to the crate root so it matches across platforms.
//! Entries that do not exist (for example the lockfile outside a workspace checkout) are left
//! out of both the hash and the `rerun-if-changed` list, because Cargo reruns a build script on
//! every build when a watched path is missing.

use sha2::{Digest, Sha256};
use std::path::{Component, Path, PathBuf};

const HASHED_ENTRIES: [&str; 3] = ["Cargo.toml", "src", "function_names"];
const WORKSPACE_LOCKFILE: &str = "../../Cargo.lock";

fn main() -> Result<(), String> {
    let crate_dir =
        PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").map_err(|error| error.to_string())?);
    let mut files: Vec<(String, PathBuf)> = Vec::new();
    for entry in HASHED_ENTRIES {
        let path = crate_dir.join(entry);
        if path.exists() {
            println!("cargo:rerun-if-changed={}", path.display());
            collect_files(&crate_dir, &path, &mut files)?;
        }
    }
    files.sort();
    let lockfile = crate_dir.join(WORKSPACE_LOCKFILE);
    if lockfile.is_file() {
        println!("cargo:rerun-if-changed={}", lockfile.display());
        files.push((WORKSPACE_LOCKFILE.to_owned(), lockfile));
    }
    let mut digest = Sha256::new();
    for (label, file) in &files {
        digest.update(label.as_bytes());
        digest.update([0]);
        digest.update(std::fs::read(file).map_err(|error| error.to_string())?);
        digest.update([0]);
    }
    let identity = format!("{:x}", digest.finalize());
    println!(
        "cargo:rustc-env=SQLBUILD_NATIVE_SOURCE_HASH={}",
        &identity[..16]
    );
    Ok(())
}

fn portable_label(crate_dir: &Path, path: &Path) -> Result<String, String> {
    let relative = path
        .strip_prefix(crate_dir)
        .map_err(|error| error.to_string())?;
    let parts: Vec<String> = relative
        .components()
        .map(|component| match component {
            Component::Normal(part) => Ok(part.to_string_lossy().into_owned()),
            other => Err(format!("unexpected path component {other:?}")),
        })
        .collect::<Result<_, _>>()?;
    Ok(parts.join("/"))
}

fn collect_files(
    crate_dir: &Path,
    path: &Path,
    files: &mut Vec<(String, PathBuf)>,
) -> Result<(), String> {
    if path.is_file() {
        files.push((portable_label(crate_dir, path)?, path.to_path_buf()));
        return Ok(());
    }
    if !path.is_dir() {
        return Ok(());
    }
    for entry in std::fs::read_dir(path).map_err(|error| error.to_string())? {
        collect_files(
            crate_dir,
            &entry.map_err(|error| error.to_string())?.path(),
            files,
        )?;
    }
    Ok(())
}
