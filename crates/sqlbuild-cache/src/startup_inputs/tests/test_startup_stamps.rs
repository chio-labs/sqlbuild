use std::path::{Path, PathBuf};

use crate::startup_inputs::main::startup_stamps::startup_stamps;
use crate::startup_inputs::models::{StartupLocations, StartupStamp};
use crate::startup_inputs::tests::test_types::StartupStampsTestCase;

#[test]
fn given_startup_locations_when_stamped_then_paths_are_absolute_listed_and_sorted_by_parts() {
    let test_cases = [StartupStampsTestCase {
        description: "relative entries, path files, missing entries and the venv configuration",
        directories: vec!["site", "./a//", "a-b", "a/b", "missing"],
        expected_stamps: vec![
            ("a", true),
            ("a/b", true),
            ("a/q.pth", true),
            ("a-b", true),
            ("a-b/x.pth", true),
            ("missing", false),
            ("pyvenv.cfg", false),
            ("site", true),
            ("site/.pth", true),
            ("site/one.pth", true),
        ],
    }];
    for test_case in test_cases {
        let directory = tempfile::tempdir().expect("temporary directory");
        let root: PathBuf = std::fs::canonicalize(directory.path()).expect("resolved");
        for folder in ["a", "a-b", "a/b", "site"] {
            std::fs::create_dir_all(root.join(folder)).expect("folder");
        }
        for file in [
            "site/one.pth",
            "site/.pth",
            "site/two.pth.bak",
            "a/q.pth",
            "a-b/x.pth",
        ] {
            std::fs::write(root.join(file), "x\n").expect("file");
        }
        let locations = StartupLocations {
            directories: test_case.directories.iter().map(PathBuf::from).collect(),
            files: vec![root.join("site/one.pth")],
            prefixes: vec![root.clone()],
        };
        let stamps: Vec<StartupStamp> = startup_stamps(&locations, &root).expect("stamps");
        let listed: Vec<(String, bool)> = stamps
            .iter()
            .map(|stamp| {
                let relative: &Path = stamp.path.strip_prefix(&root).unwrap_or(&stamp.path);
                (
                    relative.to_string_lossy().into_owned(),
                    stamp.size.is_some(),
                )
            })
            .collect();
        let listed: Vec<(&str, bool)> = listed
            .iter()
            .map(|(path, present)| (path.as_str(), *present))
            .collect();
        assert_eq!(
            listed, test_case.expected_stamps,
            "{}",
            test_case.description
        );
    }
}
