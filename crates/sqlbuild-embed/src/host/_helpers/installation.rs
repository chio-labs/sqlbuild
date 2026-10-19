//! The installation an interpreter belongs to and the shared libpython in it.

use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use crate::host::constants::{
    LIBRARY_DIRECTORIES, MINIMUM_VERSION_PARTS, PROBE_SCRIPT, SHARED_BUILD, VENV_CONFIG,
};
use crate::host::models::{EmbeddableInterpreter, HostDiscovery, LocatedHost};

/// The `pyvenv.cfg` paths CPython checks for an interpreter: beside it, then one level up.
pub(crate) fn venv_config_paths(interpreter: &Path) -> Vec<PathBuf> {
    let directory: Option<&Path> = interpreter.parent();
    [directory, directory.and_then(Path::parent)]
        .into_iter()
        .flatten()
        .map(|directory| directory.join(VENV_CONFIG))
        .collect()
}

fn is_number(part: &str) -> bool {
    !part.is_empty() && part.bytes().all(|byte| byte.is_ascii_digit())
}

/// `3.12` or `3.12.13` from a version such as `3.12.13.final.0`, if it is one.
pub(crate) fn release_version(text: &str) -> Option<String> {
    let parts: Vec<&str> = text
        .trim()
        .split('.')
        .take(3)
        .take_while(|part| is_number(part))
        .collect();
    (parts.len() >= MINIMUM_VERSION_PARTS).then(|| parts.join("."))
}

/// The base interpreter directory and recorded version of a venv's `pyvenv.cfg` text.
pub(crate) fn parse_venv_config(text: &str) -> (Option<PathBuf>, Option<String>) {
    let mut home: Option<PathBuf> = None;
    let mut version: Option<String> = None;
    for line in text.lines() {
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        match key.trim().to_ascii_lowercase().as_str() {
            "home" => home = Some(PathBuf::from(value.trim())),
            "version" | "version_info" => version = version.or_else(|| release_version(value)),
            _ => {}
        }
    }
    (home, version)
}

/// The minor version of a `3.N` or `3.N.P` version.
pub(crate) fn minor_version(version: &str) -> Option<u32> {
    let minor: &str = version.strip_prefix("3.")?.split('.').next()?;
    let Ok(minor) = minor.parse::<u32>() else {
        return None;
    };
    Some(minor)
}

/// The text of the first `pyvenv.cfg` CPython would read for `interpreter`.
fn venv_config(interpreter: &Path) -> Option<String> {
    for path in venv_config_paths(interpreter) {
        if let Ok(text) = std::fs::read_to_string(path) {
            return Some(text);
        }
    }
    None
}

/// The installation prefix and version of `interpreter`, from its venv or its resolved path.
fn installation(interpreter: &Path) -> Result<(PathBuf, Option<String>), String> {
    if let Some(text) = venv_config(interpreter) {
        let (home, version) = parse_venv_config(&text);
        let home: PathBuf =
            home.ok_or_else(|| format!("the venv of {} names no home", interpreter.display()))?;
        let prefix: PathBuf = home.parent().unwrap_or(&home).to_path_buf();
        return Ok((prefix, version));
    }
    let resolved: PathBuf = std::fs::canonicalize(interpreter)
        .map_err(|error| format!("cannot resolve {}: {error}", interpreter.display()))?;
    let version: Option<String> = resolved
        .file_name()
        .and_then(|name| name.to_str())
        .and_then(|name| name.strip_prefix("python"))
        .and_then(release_version);
    let prefix: PathBuf = resolved
        .parent()
        .and_then(Path::parent)
        .ok_or_else(|| format!("{} has no installation prefix", resolved.display()))?
        .to_path_buf();
    Ok((prefix, version))
}

/// The library directories of an installation prefix, including the Debian multiarch one.
fn library_directories(prefix: &Path) -> Vec<PathBuf> {
    let mut directories: Vec<PathBuf> = LIBRARY_DIRECTORIES
        .iter()
        .map(|directory| prefix.join(directory))
        .collect();
    if matches!(std::env::consts::ARCH, "x86_64" | "aarch64") {
        let triple = format!("{}-linux-gnu", std::env::consts::ARCH);
        directories.push(prefix.join("lib").join(triple));
    }
    directories
}

fn library_candidates(directory: &Path, names: &[String]) -> Vec<PathBuf> {
    names.iter().map(|name| directory.join(name)).collect()
}

/// The first shared libpython 3.`minor` in the installation's library directories.
pub(crate) fn installed_library(prefix: &Path, minor: u32) -> Option<PathBuf> {
    let names = [
        format!("libpython3.{minor}.so.1.0"),
        format!("libpython3.{minor}.so"),
    ];
    library_directories(prefix)
        .iter()
        .flat_map(|directory| library_candidates(directory, &names))
        .find(|candidate| candidate.is_file())
}

/// Whether `path` is inside `directory` once both are resolved.
fn resolves_inside(path: &Path, directory: &Path) -> bool {
    match (
        std::fs::canonicalize(path),
        std::fs::canonicalize(directory),
    ) {
        (Ok(path), Ok(directory)) => path.starts_with(directory),
        _ => false,
    }
}

fn uncacheable(reason: String) -> LocatedHost {
    LocatedHost {
        found: HostDiscovery::Exec(reason),
        cacheable: false,
        watched: None,
    }
}

fn embeddable(interpreter: &Path, library: PathBuf, version: String) -> LocatedHost {
    LocatedHost {
        found: HostDiscovery::Embeddable(EmbeddableInterpreter {
            interpreter: interpreter.to_path_buf(),
            library: library.clone(),
            version,
        }),
        cacheable: true,
        watched: Some(library),
    }
}

/// Ask the interpreter for its shared library when the usual places hold none.
fn probe_library(interpreter: &Path, version: Option<String>) -> LocatedHost {
    let output = Command::new(interpreter)
        .args(["-I", "-c", PROBE_SCRIPT])
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .output();
    let output = match output {
        Ok(output) if output.status.success() => output,
        Ok(_) => {
            return uncacheable(format!(
                "{} failed to describe itself",
                interpreter.display()
            ));
        }
        Err(error) => return uncacheable(format!("cannot run {}: {error}", interpreter.display())),
    };
    let text: String = String::from_utf8_lossy(&output.stdout).into_owned();
    let lines: Vec<&str> = text.lines().collect();
    let [shared, directory, name, base_prefix, minor_text] = lines.as_slice() else {
        return uncacheable(format!(
            "{} described itself unexpectedly",
            interpreter.display()
        ));
    };
    if *shared != SHARED_BUILD || directory.is_empty() || name.is_empty() {
        return LocatedHost {
            found: HostDiscovery::Exec(format!(
                "{} has no shared libpython",
                interpreter.display()
            )),
            cacheable: true,
            watched: None,
        };
    }
    let library: PathBuf = Path::new(directory).join(name);
    if !library.is_file() || !resolves_inside(&library, Path::new(base_prefix)) {
        return LocatedHost {
            found: HostDiscovery::Exec(format!(
                "{} has no shared libpython in its installation",
                interpreter.display()
            )),
            cacheable: true,
            watched: Some(library),
        };
    }
    embeddable(
        interpreter,
        library,
        version.unwrap_or_else(|| (*minor_text).to_owned()),
    )
}

/// How `interpreter` can be started, and how long that answer holds.
pub(crate) fn locate_library(interpreter: &Path) -> LocatedHost {
    let (prefix, version) = match installation(interpreter) {
        Ok(found) => found,
        Err(reason) => return uncacheable(reason),
    };
    let library: Option<PathBuf> = version
        .as_deref()
        .and_then(minor_version)
        .and_then(|minor| installed_library(&prefix, minor));
    match (library, version) {
        (Some(library), Some(version)) => embeddable(interpreter, library, version),
        (_, version) => probe_library(interpreter, version),
    }
}
