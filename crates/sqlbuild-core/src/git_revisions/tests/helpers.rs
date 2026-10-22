use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicUsize, Ordering};

static NEXT_DIRECTORY: AtomicUsize = AtomicUsize::new(0);

/// A fresh empty directory under the system temporary directory.
pub(super) fn scratch_directory(label: &str) -> PathBuf {
    let directory: PathBuf = std::env::temp_dir().join(format!(
        "sqlbuild-git-revisions-{label}-{}-{}",
        std::process::id(),
        NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed)
    ));
    let _ = std::fs::remove_dir_all(&directory);
    std::fs::create_dir_all(&directory).expect("the scratch directory is created");
    directory
}

/// Run git in `directory` with a fixed identity, returning trimmed stdout.
pub(super) fn git(directory: &Path, arguments: &[&str]) -> String {
    let output = Command::new("git")
        .current_dir(directory)
        .args([
            "-c",
            "user.name=Example",
            "-c",
            "user.email=dev@example.com",
        ])
        .args([
            "-c",
            "init.defaultBranch=main",
            "-c",
            "commit.gpgsign=false",
        ])
        .args(arguments)
        .output()
        .expect("git runs");
    assert!(
        output.status.success(),
        "git {arguments:?} failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    String::from_utf8_lossy(&output.stdout).trim().to_owned()
}

/// Write `contents` to `relative` under `root`, creating parent directories.
pub(super) fn write(root: &Path, relative: &str, contents: &str) {
    let path: PathBuf = root.join(relative);
    std::fs::create_dir_all(path.parent().expect("a parent")).expect("parents are created");
    std::fs::write(path, contents).expect("the file is written");
}

/// A repository with a project in `warehouse/` and branches `main` and `feature`; root and `main`.
pub(super) fn project_repository() -> (PathBuf, String) {
    let root: PathBuf = scratch_directory("repo");
    git(&root, &["init", "--quiet"]);
    write(
        &root,
        "warehouse/sqlbuild_project.toml",
        "name = \"orders\"\n",
    );
    write(
        &root,
        "warehouse/models/orders.sql",
        "SELECT 1 AS order_id\n",
    );
    git(&root, &["add", "."]);
    git(&root, &["commit", "--quiet", "-m", "orders"]);
    let main: String = git(&root, &["rev-parse", "HEAD"]);
    git(&root, &["checkout", "--quiet", "-b", "feature"]);
    write(
        &root,
        "warehouse/models/orders.sql",
        "SELECT 2 AS order_id\n",
    );
    write(
        &root,
        "warehouse/models/customers.sql",
        "SELECT 1 AS customer_id\n",
    );
    git(&root, &["add", "."]);
    git(&root, &["commit", "--quiet", "-m", "customers"]);
    (root, main)
}

/// The text of `path`, or `None` when it is absent.
pub(super) fn read(path: &Path) -> Option<String> {
    std::fs::read_to_string(path).ok()
}
