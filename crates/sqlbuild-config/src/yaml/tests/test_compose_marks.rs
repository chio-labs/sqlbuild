use crate::yaml::tests::helpers::{owned_marks, scalar_marks};
use crate::yaml::tests::test_types::ComposeMarksTestCase;

#[test]
fn given_yaml_documents_when_composing_then_scalar_marks_cover_their_values() {
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
            description: "a byte order mark counts in the marks of the original text",
            text: "\u{feff}k: v",
            expected_scalars: Ok(&[(1, 2, "k"), (4, 5, "v")]),
        },
        ComposeMarksTestCase {
            description: "an anchored scalar starts at its value and its alias is the same node",
            text: "a: &x v\nb: *x\n",
            expected_scalars: Ok(&[(0, 1, "a"), (6, 7, "v"), (8, 9, "b")]),
        },
        ComposeMarksTestCase {
            description: "a scalar with a tag and an anchor starts at its value",
            text: "a: !!str 12\nb: !!str &y q\nc: &t !!str 'x'\n",
            expected_scalars: Ok(&[
                (0, 1, "a"),
                (9, 11, "12"),
                (12, 13, "b"),
                (24, 25, "q"),
                (26, 27, "c"),
                (38, 41, "x"),
            ]),
        },
        ComposeMarksTestCase {
            description: "a verbatim tag with a comma and an anchored block scalar",
            text: "x: !<tag:yaml.org,2002:str> v\nc: &c |\n  txt\n",
            expected_scalars: Ok(&[(0, 1, "x"), (28, 29, "v"), (30, 31, "c"), (36, 44, "txt\n")]),
        },
        ComposeMarksTestCase {
            description: "anchors inside flow and block collections",
            text: "k: [&e a, *e]\nm: &n\n  - &o x\n",
            expected_scalars: Ok(&[(0, 1, "k"), (7, 8, "a"), (14, 15, "m"), (27, 28, "x")]),
        },
        ComposeMarksTestCase {
            description: "a tagged value after a double-quoted value holding ' # ' starts at its quote",
            text: "sources: [{name: raw_orders, description: \"Orders # archived\", expression: !!str \"(SELECT 1 AS id)\"}]\n",
            expected_scalars: Ok(&[
                (0, 7, "sources"),
                (11, 15, "name"),
                (17, 27, "raw_orders"),
                (29, 40, "description"),
                (42, 61, "Orders # archived"),
                (63, 73, "expression"),
                (81, 99, "(SELECT 1 AS id)"),
            ]),
        },
        ComposeMarksTestCase {
            description: "a tagged value after a single-quoted value holding ' # ' starts at its quote",
            text: "sources: [{name: raw_orders, description: 'Orders # archived', expression: !!str '(SELECT 1 AS id)'}]\n",
            expected_scalars: Ok(&[
                (0, 7, "sources"),
                (11, 15, "name"),
                (17, 27, "raw_orders"),
                (29, 40, "description"),
                (42, 61, "Orders # archived"),
                (63, 73, "expression"),
                (81, 99, "(SELECT 1 AS id)"),
            ]),
        },
        ComposeMarksTestCase {
            description: "comments between properties and the value are skipped",
            text: "k: &a  # real comment\n  v\nq: \"x # y\"  # c\nr: !!str &b 'z' # c\n",
            expected_scalars: Ok(&[
                (0, 1, "k"),
                (24, 25, "v"),
                (26, 27, "q"),
                (29, 36, "x # y"),
                (42, 43, "r"),
                (54, 57, "z"),
            ]),
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
