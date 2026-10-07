use crate::tree::main::rglob::rglob;
use crate::tree::models::ProjectTree;
use crate::tree::tests::test_types::GlobTestCase;
use std::fs;
use std::path::Path;

fn write_file(project: &Path, relative_path: &str) {
    let path = project.join(relative_path);
    fs::create_dir_all(path.parent().expect("parent directory")).expect("directories");
    fs::write(path, "MODEL ();\nSELECT 1").expect("file");
}

#[cfg(unix)]
fn link(project: &Path, (link, target): (&str, &str)) {
    std::os::unix::fs::symlink(project.join(target), project.join(link)).expect("symlink");
}

/// Build the case's project and glob `models/` for its suffix.
pub(super) fn globbed_paths(test_case: &GlobTestCase) -> Vec<String> {
    let project = tempfile::tempdir().expect("temporary project");
    test_case
        .files
        .iter()
        .for_each(|relative_path| write_file(project.path(), relative_path));
    test_case.directories.iter().for_each(|relative_path| {
        fs::create_dir_all(project.path().join(relative_path)).expect("directory")
    });
    #[cfg(unix)]
    test_case
        .links
        .iter()
        .for_each(|pair| link(project.path(), *pair));
    let tree = ProjectTree::new(project.path());
    rglob(&tree, "models", |entry| {
        entry.name.ends_with(test_case.suffix)
    })
    .expect("walk")
}
