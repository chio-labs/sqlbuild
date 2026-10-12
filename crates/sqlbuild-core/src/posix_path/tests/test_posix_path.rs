use crate::posix_path::main::posix_join::posix_join;
use crate::posix_path::main::posix_name::posix_name;
use crate::posix_path::main::posix_parent::posix_parent;
use crate::posix_path::main::posix_parts::posix_parts;
use crate::posix_path::main::posix_suffix::posix_suffix;
use crate::posix_path::tests::test_types::PosixPathTestCase;

#[test]
fn given_paths_when_reading_pure_posix_parts_then_they_match_pathlib() {
    let test_cases = [
        PosixPathTestCase {
            description: "a relative file path",
            path: "models/a.sql",
            expected_parts: &["models", "a.sql"],
            expected_parent: "models",
            expected_name: "a.sql",
            expected_suffix: ".sql",
        },
        PosixPathTestCase {
            description: "current, empty and trailing components are dropped",
            path: "./a//b/",
            expected_parts: &["a", "b"],
            expected_parent: "a",
            expected_name: "b",
            expected_suffix: "",
        },
        PosixPathTestCase {
            description: "an absolute path keeps its root",
            path: "/abs/x.yml",
            expected_parts: &["/", "abs", "x.yml"],
            expected_parent: "/abs",
            expected_name: "x.yml",
            expected_suffix: ".yml",
        },
        PosixPathTestCase {
            description: "exactly two leading slashes are their own root",
            path: "//net/x",
            expected_parts: &["//", "net", "x"],
            expected_parent: "//net",
            expected_name: "x",
            expected_suffix: "",
        },
        PosixPathTestCase {
            description: "three leading slashes collapse to one root",
            path: "///three/x",
            expected_parts: &["/", "three", "x"],
            expected_parent: "/three",
            expected_name: "x",
            expected_suffix: "",
        },
        PosixPathTestCase {
            description: "the current directory has no parts",
            path: ".",
            expected_parts: &[],
            expected_parent: ".",
            expected_name: "",
            expected_suffix: "",
        },
        PosixPathTestCase {
            description: "empty text is the current directory",
            path: "",
            expected_parts: &[],
            expected_parent: ".",
            expected_name: "",
            expected_suffix: "",
        },
        PosixPathTestCase {
            description: "a parent component is kept",
            path: "a/..",
            expected_parts: &["a", ".."],
            expected_parent: "a",
            expected_name: "..",
            expected_suffix: "",
        },
        PosixPathTestCase {
            description: "a leading-dot name has a suffix only before Python 3.14",
            path: "..a",
            expected_parts: &["..a"],
            expected_parent: ".",
            expected_name: "..a",
            expected_suffix: "",
        },
        PosixPathTestCase {
            description: "a trailing dot is a suffix only from Python 3.14",
            path: "d/a.",
            expected_parts: &["d", "a."],
            expected_parent: "d",
            expected_name: "a.",
            expected_suffix: ".",
        },
        PosixPathTestCase {
            description: "the last dot starts the suffix",
            path: "d/...b.c",
            expected_parts: &["d", "...b.c"],
            expected_parent: "d",
            expected_name: "...b.c",
            expected_suffix: ".c",
        },
        PosixPathTestCase {
            description: "non-ASCII components are whole parts",
            path: "caf\u{e9}/\u{1F600}.sql",
            expected_parts: &["caf\u{e9}", "\u{1F600}.sql"],
            expected_parent: "caf\u{e9}",
            expected_name: "\u{1F600}.sql",
            expected_suffix: ".sql",
        },
        PosixPathTestCase {
            description: "a bare root is its own parent",
            path: "/",
            expected_parts: &["/"],
            expected_parent: "/",
            expected_name: "",
            expected_suffix: "",
        },
    ];
    for test_case in test_cases {
        let parts: Vec<&str> = posix_parts(test_case.path);

        assert_eq!(
            (
                parts.as_slice(),
                posix_parent(test_case.path),
                posix_name(test_case.path),
                posix_suffix(test_case.path),
            ),
            (
                test_case.expected_parts,
                test_case.expected_parent.to_owned(),
                test_case.expected_name,
                test_case.expected_suffix,
            ),
            "{}",
            test_case.description
        );
        assert_eq!(
            posix_parts(&posix_join(&parts)),
            parts,
            "{}",
            test_case.description
        );
    }
}
