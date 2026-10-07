use crate::declarations::models::DeclarationKind;
use crate::declarations::tests::helpers::{layout_rows, owned_facts, owned_groups};
use crate::declarations::tests::test_types::LayoutTestCase;

#[test]
fn given_declaration_layouts_when_scanning_then_facts_and_failures_match_python() {
    let test_cases = [
        LayoutTestCase {
            kind: None,
            description: "global, inherited, grouped and local roots sort by relative path",
            files: &[
                "macros/text.py",
                "macros/__init__.py",
                "enums/status.sql",
                "models/marts/_enums/local.sql",
                "models/marts/_sqlbuild/constants/limits.sql",
                "models/marts/_sqlbuild/audits/generic/positive.sql",
            ],
            directories: &[],
            expected_facts: Ok(&[
                ("enums/status.sql", "enum", "global", "enums", None, "enums"),
                (
                    "macros/text.py",
                    "macro",
                    "global",
                    "macros",
                    None,
                    "macros",
                ),
                (
                    "models/marts/_enums/local.sql",
                    "enum",
                    "local",
                    "models",
                    Some("models/marts"),
                    "models/marts/_enums",
                ),
                (
                    "models/marts/_sqlbuild/constants/limits.sql",
                    "constant",
                    "inherited",
                    "models",
                    Some("models/marts"),
                    "models/marts/_sqlbuild/constants",
                ),
            ]),
            expected_groups: Ok(&[("models", "models/marts/_sqlbuild")]),
        },
        LayoutTestCase {
            kind: None,
            description: "a declaration group directly below a canonical root fails",
            files: &["models/_sqlbuild/macros/text.py"],
            directories: &[],
            expected_facts: Err(
                "Grouped declaration root models/_sqlbuild/ must be below a concrete owner \
                 directory; use the project-wide macros/, enums/, constants/, audits/, \
                 schemas/, or hooks/ root instead",
            ),
            expected_groups: Ok(&[]),
        },
        LayoutTestCase {
            kind: None,
            description: "a nested declaration root fails in both scans",
            files: &["models/a/_enums/macros/x.py"],
            directories: &["schemas/enums"],
            expected_facts: Err(
                "Declaration root models/a/_enums/macros/ is nested inside another declaration \
                 tree",
            ),
            expected_groups: Err(
                "Declaration directory schemas/enums/ is not allowed inside the project-wide \
                 schemas/ role; scoped declarations belong under <folder>/_sqlbuild/ below a \
                 resource tree",
            ),
        },
        LayoutTestCase {
            kind: None,
            description: "unsupported group and role entries list every entry",
            files: &[
                "models/a/_sqlbuild/notes.txt",
                "audits/x.sql",
                "audits/.keep",
            ],
            directories: &["models/a/_sqlbuild/extra"],
            expected_facts: Err(
                "Declaration group models/a/_sqlbuild/ contains unsupported entries: \
                 models/a/_sqlbuild/extra, models/a/_sqlbuild/notes.txt",
            ),
            expected_groups: Err(
                "Unsupported entries in audits/: audits/x.sql; audit files must live in \
                 audits/generic/ or audits/singular/",
            ),
        },
        LayoutTestCase {
            kind: None,
            description: "local singular audits and unknown hook roles fail the named layout",
            files: &[],
            directories: &[
                "models/a/_sqlbuild/_audits/singular",
                "models/b/_sqlbuild/hooks/x",
            ],
            expected_facts: Ok(&[]),
            expected_groups: Err(
                "models/a/_sqlbuild/_audits/singular/ is invalid: singular audits are never used \
                 by name, so folder-only visibility has no meaning; use \
                 _sqlbuild/audits/singular/",
            ),
        },
        LayoutTestCase {
            kind: None,
            description: "a scoped root at the project root fails",
            files: &["_macros/text.py"],
            directories: &[],
            expected_facts: Err(
                "Scoped declaration root _macros/ must be below a canonical authored root",
            ),
            expected_groups: Ok(&[]),
        },
        LayoutTestCase {
            kind: Some(DeclarationKind::Enum),
            description: "an isolated kind skips the misplaced roots of other kinds",
            files: &[
                "_macros/text.py",
                "enums/status.sql",
                "models/a/macros/x.py",
            ],
            directories: &[],
            expected_facts: Ok(&[("enums/status.sql", "enum", "global", "enums", None, "enums")]),
            expected_groups: Ok(&[]),
        },
        LayoutTestCase {
            kind: Some(DeclarationKind::Constant),
            description: "an isolated kind still rejects a root nested in its own tree",
            files: &["models/a/constants/_enums/x.sql"],
            directories: &[],
            expected_facts: Err(
                "Declaration root models/a/constants/_enums/ is nested inside another \
                 declaration tree",
            ),
            expected_groups: Ok(&[]),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            layout_rows(&test_case),
            (
                owned_facts(test_case.expected_facts),
                owned_groups(test_case.expected_groups)
            ),
            "{}",
            test_case.description
        );
    }
}
