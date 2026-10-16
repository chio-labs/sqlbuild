use std::path::{Path, PathBuf};

use crate::project_tree::errors::RelativePartsError;
use crate::project_tree::main::project_relative_parts::project_relative_parts;
use crate::project_tree::main::project_tree_children::project_tree_children;
use crate::project_tree::main::project_tree_descendants::project_tree_descendants;
use crate::project_tree::main::project_tree_glob::project_tree_glob;
use crate::project_tree::main::tracked_text_path::tracked_text_path;
use crate::project_tree::tests::test_types::{
    PathSelectionTestCase, RelativePartsTestCase, TrackedTextTestCase,
};

const VALUES: [&str; 6] = [
    "models",
    "models/marts",
    "models/marts/orders.sql",
    "models/a.sql",
    "rules",
    "readme.md",
];

#[test]
fn given_listed_paths_when_selecting_then_children_descendants_and_globs_match_pathlib() {
    let test_cases = [
        PathSelectionTestCase {
            description: "the project root",
            argument: None,
            expected_children: vec!["models", "rules", "readme.md"],
            expected_descendants: VALUES.to_vec(),
            expected_glob: vec![],
        },
        PathSelectionTestCase {
            description: "a folder spelled with dots and slashes",
            argument: Some("./models//"),
            expected_children: vec!["models/marts", "models/a.sql"],
            expected_descendants: vec!["models/marts", "models/marts/orders.sql", "models/a.sql"],
            expected_glob: vec![],
        },
        PathSelectionTestCase {
            description: "a star pattern crossing folders",
            argument: Some("*.sql"),
            expected_children: vec![],
            expected_descendants: vec![],
            expected_glob: vec!["models/marts/orders.sql", "models/a.sql"],
        },
        PathSelectionTestCase {
            description: "a negated set",
            argument: Some("[!m]*"),
            expected_children: vec![],
            expected_descendants: vec![],
            expected_glob: vec!["rules", "readme.md"],
        },
    ];
    let values: Vec<&Path> = VALUES.iter().map(Path::new).collect();
    let pick = |indexes: Vec<usize>| -> Vec<&str> {
        indexes.into_iter().map(|index| VALUES[index]).collect()
    };
    for test_case in test_cases {
        let argument: &Path = Path::new(test_case.argument.unwrap_or(""));
        assert_eq!(
            (
                pick(project_tree_children(&values, argument)),
                pick(project_tree_descendants(
                    &values,
                    test_case.argument.map(Path::new)
                )),
                pick(project_tree_glob(&values, argument)),
            ),
            (
                test_case.expected_children,
                test_case.expected_descendants,
                test_case.expected_glob
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_paths_when_made_project_relative_then_parts_follow_relative_to() {
    let test_cases = [
        RelativePartsTestCase {
            description: "a relative path keeps its parts",
            path: "models/../a.sql",
            resolved: "",
            under: None,
            expected_parts: Ok(vec!["models", "..", "a.sql"]),
        },
        RelativePartsTestCase {
            description: "an absolute path inside the project",
            path: "/project/link/a.sql",
            resolved: "/project/models/a.sql",
            under: Some("models"),
            expected_parts: Ok(vec!["a.sql"]),
        },
        RelativePartsTestCase {
            description: "an absolute path outside the project",
            path: "/elsewhere/a.sql",
            resolved: "/elsewhere/a.sql",
            under: None,
            expected_parts: Err(RelativePartsError::Escapes),
        },
        RelativePartsTestCase {
            description: "a path outside the requested folder",
            path: "models/a.sql",
            resolved: "",
            under: Some("rules"),
            expected_parts: Err(RelativePartsError::NotBeneath),
        },
        RelativePartsTestCase {
            description: "a relative path is beneath the current folder",
            path: "a.sql",
            resolved: "",
            under: Some("."),
            expected_parts: Ok(vec!["a.sql"]),
        },
    ];
    for test_case in test_cases {
        let parts = project_relative_parts(
            Path::new(test_case.path),
            Path::new("/project"),
            test_case.under.map(Path::new),
            |_| Ok::<PathBuf, ()>(PathBuf::from(test_case.resolved)),
        )
        .map(|parts| {
            parts
                .into_iter()
                .map(|part| part.to_string_lossy().into_owned())
                .collect::<Vec<String>>()
        });
        assert_eq!(
            parts
                .as_ref()
                .map(|parts| parts.iter().map(String::as_str).collect::<Vec<&str>>())
                .map_err(Clone::clone),
            test_case.expected_parts,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_file_names_when_checking_tracked_text_then_only_known_suffixes_count() {
    let test_cases = [
        TrackedTextTestCase {
            description: "a SQL model",
            path: "models/a.sql",
            expected_tracked: true,
        },
        TrackedTextTestCase {
            description: "an uppercase suffix",
            path: "models/A.YML",
            expected_tracked: true,
        },
        TrackedTextTestCase {
            description: "a hidden name without a suffix",
            path: "models/.sql",
            expected_tracked: false,
        },
        TrackedTextTestCase {
            description: "a markdown file",
            path: "readme.md",
            expected_tracked: false,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            tracked_text_path(Path::new(test_case.path)),
            test_case.expected_tracked,
            "{}",
            test_case.description
        );
    }
}
