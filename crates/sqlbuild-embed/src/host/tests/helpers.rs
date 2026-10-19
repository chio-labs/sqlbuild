use std::fs;
use std::path::{Path, PathBuf};

use crate::host::_helpers::cache::cache_file;
use crate::host::main::forget_host::forget_host;
use crate::host::models::{EmbeddableInterpreter, HostDiscovery, LocatedHost};
use crate::host::tests::test_types::StaticVenv;

/// A temporary directory and its resolved path, so links and reported paths compare equal.
pub(super) fn temporary_root() -> (tempfile::TempDir, PathBuf) {
    let directory = tempfile::tempdir().expect("tempdir");
    let root: PathBuf = fs::canonicalize(directory.path()).expect("resolved");
    (directory, root)
}

/// Write `contents` to `path`, creating its directories, and make it executable.
pub(super) fn write_executable(path: &Path, contents: &str) {
    fs::create_dir_all(path.parent().expect("parent")).expect("directories");
    fs::write(path, contents).expect("write");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o755)).expect("chmod");
    }
}

/// Create a file at `path` with its directories.
pub(super) fn touch(path: &Path) {
    fs::create_dir_all(path.parent().expect("parent")).expect("directories");
    fs::write(path, b"").expect("write");
}

/// `text` with `<root>` replaced by `root` and `<arch>` by this CPU's architecture.
pub(super) fn rooted(text: &str, root: &Path) -> String {
    text.replace("<root>", &root.display().to_string())
        .replace("<arch>", std::env::consts::ARCH)
}

/// A link at `link` to `target`, both below `root`.
pub(super) fn link(root: &Path, target: &str, link: &str) -> PathBuf {
    let link: PathBuf = root.join(link);
    fs::create_dir_all(link.parent().expect("parent")).expect("directories");
    #[cfg(unix)]
    std::os::unix::fs::symlink(root.join(target), &link).expect("symlink");
    link
}

/// A venv under `root` whose base installation is `root/base`, with `venv/bin/python`.
pub(super) fn venv(root: &Path, version_line: &str) -> PathBuf {
    let base_bin: PathBuf = root.join("base").join("bin");
    write_executable(&base_bin.join("python3.12"), "#!/bin/sh\n");
    let venv: PathBuf = root.join("venv");
    let interpreter: PathBuf = venv.join("bin").join("python");
    write_executable(&interpreter, "#!/bin/sh\n");
    fs::write(
        venv.join("pyvenv.cfg"),
        format!(
            "home = {}\nimplementation = CPython\n{version_line}\ninclude-system-site-packages = false\n",
            base_bin.display()
        ),
    )
    .expect("pyvenv.cfg");
    interpreter
}

/// A fake interpreter at `path` that counts its runs in `counter` and describes itself as `lines`.
pub(super) fn describing_interpreter(path: &Path, counter: &Path, lines: &[String]) {
    let output: String = lines.join("\\n");
    write_executable(
        path,
        &format!(
            "#!/bin/sh\necho run >> '{}'\nprintf '{output}\\n'\n",
            counter.display()
        ),
    );
}

/// How many times the fake interpreter writing to `counter` ran.
pub(super) fn runs(counter: &Path) -> usize {
    fs::read_to_string(counter)
        .unwrap_or_default()
        .lines()
        .count()
}

/// A venv whose base interpreter has no shared libpython, with a `#!` console script.
pub(super) fn static_venv(root: &Path) -> StaticVenv {
    let interpreter: PathBuf = venv(root, "version_info = 3.12");
    let runs: PathBuf = root.join("runs");
    let answer: Vec<String> = ["0", "", "", "<root>/base", "3.12"]
        .iter()
        .map(|line| rooted(line, root))
        .collect();
    describing_interpreter(&interpreter, &runs, &answer);
    let script: PathBuf = root.join("venv/bin/sqlbuild-python");
    write_executable(
        &script,
        &format!("#!{}\nimport sys\n", interpreter.display()),
    );
    StaticVenv {
        root: root.to_path_buf(),
        interpreter,
        script,
        cache: root.join("cache"),
        runs,
    }
}

/// Leave the static venv and its cache as they are.
pub(super) fn unchanged(_venv: &StaticVenv) {}

/// Add a line to the static venv's `pyvenv.cfg`.
pub(super) fn edit_venv_config(venv: &StaticVenv) {
    let config: PathBuf = venv.root.join("venv/pyvenv.cfg");
    let text: String = fs::read_to_string(&config).expect("config");
    fs::write(&config, format!("{text}prompt = shop\n")).expect("config");
}

/// Forget the static venv's cached discovery.
pub(super) fn forget(venv: &StaticVenv) {
    forget_host(Some(&venv.cache), &venv.interpreter);
}

/// Overwrite the static venv's cache file with text that is not a cache entry.
pub(super) fn corrupt_cache(venv: &StaticVenv) {
    fs::write(
        cache_file(&venv.cache, &venv.interpreter),
        "not a cache entry\n",
    )
    .expect("write");
}

/// The discovery of an interpreter with no shared libpython, below `root`.
pub(super) fn static_exec(root: &Path) -> HostDiscovery {
    HostDiscovery::Exec(rooted(
        "<root>/venv/bin/python has no shared libpython",
        root,
    ))
}

/// An embeddable discovery of `root/<interpreter>` with `root/<library>` at `version`.
pub(super) fn embeddable(
    root: &Path,
    interpreter: &str,
    library: &str,
    version: &str,
) -> HostDiscovery {
    HostDiscovery::Embeddable(EmbeddableInterpreter {
        interpreter: root.join(interpreter),
        library: root.join(library),
        version: version.to_owned(),
    })
}

/// A located host with the given answer, cacheability and watched file below `root`.
pub(super) fn located(
    found: HostDiscovery,
    cacheable: bool,
    watched: Option<PathBuf>,
) -> LocatedHost {
    LocatedHost {
        found,
        cacheable,
        watched,
    }
}

/// A venv whose base installation has a shared libpython 3.12.
pub(super) fn venv_with_shared_base(root: &Path) -> PathBuf {
    touch(&root.join("base/lib/libpython3.12.so.1.0"));
    venv(root, "version_info = 3.12.13")
}

/// A base interpreter reached through a `python3` link to `python3.13`.
pub(super) fn linked_base_interpreter(root: &Path) -> PathBuf {
    touch(&root.join("prefix/bin/python3.13"));
    touch(&root.join("prefix/lib/libpython3.13.so.1.0"));
    link(root, "prefix/bin/python3.13", "prefix/bin/python3")
}
