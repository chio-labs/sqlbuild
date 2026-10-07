use crate::models::{DiscoveryFailure, FailureKind, ProjectRoot};
use crate::tree::models::ProjectTree;
use crate::yaml_files::main::load_yaml_files::load_yaml_files;
use crate::yaml_files::main::load_yaml_text::load_yaml_text;
use crate::yaml_files::models::YamlFileOutcome;

pub(super) const FILE_PATH: &str = "project/sources/orders.yml";

/// The outcome of loading one file holding `contents`, with an empty display prefix.
pub(super) fn file_outcome(contents: &[u8]) -> YamlFileOutcome {
    let project = tempfile::tempdir().expect("temporary project");
    std::fs::write(project.path().join("file.yml"), contents).expect("file");
    let root = ProjectRoot {
        directory: project.path().to_path_buf(),
        display_prefix: String::new(),
    };
    let mut outcomes: Vec<YamlFileOutcome> = load_yaml_files(
        &root,
        &ProjectTree::new(project.path()),
        &["file.yml".to_owned()],
        FailureKind::Source,
    )
    .expect("no stage failure");
    outcomes.pop().expect("one outcome")
}

/// The failure message and help of loading `text`, or `None` when it loads.
pub(super) fn text_failure(text: &str) -> Option<(String, Option<String>)> {
    load_yaml_text(FILE_PATH, text, FailureKind::Source)
        .err()
        .map(|failure: DiscoveryFailure| (failure.message, failure.help))
}

/// The expected failure in the owned shape `text_failure` returns.
pub(super) fn owned_failure(
    expected: Option<(&'static str, Option<&'static str>)>,
) -> Option<(String, Option<String>)> {
    expected.map(|(message, help)| (message.to_owned(), help.map(str::to_owned)))
}
