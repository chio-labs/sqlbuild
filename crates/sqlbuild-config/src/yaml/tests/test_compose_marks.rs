use crate::yaml::tests::helpers::{owned_marks, scalar_marks};
use crate::yaml::tests::test_types::ComposeMarksTestCase;

#[test]
fn given_yaml_documents_when_composing_then_scalar_marks_match_pyyaml() {
    let test_cases = [
        ComposeMarksTestCase {
            description: "quoted and plain scalars start at their token and end after it",
            text: "a: 'single ''quoted'' value'\nb: plain value   \nc: \"multi\n  line\"\n",
            expected_scalars: Ok(&[
                (0, 1, "a"),
                (3, 28, "single 'quoted' value"),
                (29, 30, "b"),
                (32, 43, "plain value"),
                (47, 48, "c"),
                (50, 64, "multi line"),
            ]),
        },
        ComposeMarksTestCase {
            description: "block scalars start at their indicator and end after their last line break",
            text: "d: |\n  x __ref(\"y\")\n  z\ne: >-\n  folded\n\n\nf: g",
            expected_scalars: Ok(&[
                (0, 1, "d"),
                (3, 24, "x __ref(\"y\")\nz\n"),
                (24, 25, "e"),
                (27, 41, "folded"),
                (41, 42, "f"),
                (44, 45, "g"),
            ]),
        },
        ComposeMarksTestCase {
            description: "a byte order mark counts in the marks, as PyYAML's reader keeps it",
            text: "\u{feff}k: v",
            expected_scalars: Ok(&[(1, 2, "k"), (4, 5, "v")]),
        },
        ComposeMarksTestCase {
            description: "an anchored scalar starts at its anchor and its alias is the same node",
            text: "a: &x v\nb: *x\n",
            expected_scalars: Ok(&[(0, 1, "a"), (3, 7, "v"), (8, 9, "b")]),
        },
        ComposeMarksTestCase {
            description: "a scalar with a tag and an anchor starts at its first property",
            text: "a: !!str 12\nb: !!str &y q\nc: &t !!str 'x'\n",
            expected_scalars: Ok(&[
                (0, 1, "a"),
                (3, 11, "12"),
                (12, 13, "b"),
                (15, 25, "q"),
                (26, 27, "c"),
                (29, 41, "x"),
            ]),
        },
        ComposeMarksTestCase {
            description: "a verbatim tag with a comma and an anchored block scalar",
            text: "x: !<tag:yaml.org,2002:str> v\nc: &c |\n  txt\n",
            expected_scalars: Ok(&[(0, 1, "x"), (3, 29, "v"), (30, 31, "c"), (33, 44, "txt\n")]),
        },
        ComposeMarksTestCase {
            description: "anchors inside flow and block collections",
            text: "k: [&e a, *e]\nm: &n\n  - &o x\n",
            expected_scalars: Ok(&[(0, 1, "k"), (4, 8, "a"), (14, 15, "m"), (24, 28, "x")]),
        },
        ComposeMarksTestCase {
            description: "a quoted scalar ends at its closing quote, before spaces and a comment",
            text: "k: 'it''s'   # 'x'\nd: \"a \\\" b\"  \n",
            expected_scalars: Ok(&[
                (0, 1, "k"),
                (3, 10, "it's"),
                (19, 20, "d"),
                (22, 30, "a \" b"),
            ]),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            scalar_marks(test_case.text),
            owned_marks(test_case.expected_scalars),
            "{}",
            test_case.description
        );
    }
}
