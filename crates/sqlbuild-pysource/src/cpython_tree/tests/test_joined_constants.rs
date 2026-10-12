use crate::cpython_tree::main::parse_cpython_module::parse_cpython_module;
use crate::cpython_tree::main::source_position::source_position;
use crate::cpython_tree::main::walk_breadth_first::walk_breadth_first;
use crate::cpython_tree::models::{CpythonNode, ParsedSource};
use crate::cpython_tree::tests::test_types::JoinedConstantTestCase;

/// Expectations recorded from CPython 3.12, 3.13 and 3.14, which agree.
#[test]
fn given_interpolated_strings_when_walking_then_constants_merge_as_in_cpython() {
    let test_cases = [
        JoinedConstantTestCase {
            description: "debug text merges with the literal before it",
            source: "f\"a{q=}b\"",
            expected_constants: &[("aq=", 1, 2), ("b", 1, 7)],
        },
        JoinedConstantTestCase {
            description: "debug text keeps its spaces and starts after the brace",
            source: "f\"{ q = }\"",
            expected_constants: &[(" q = ", 1, 3)],
        },
        JoinedConstantTestCase {
            description: "implicit concatenation merges across parts",
            source: "f\"a\" f\"b{x}\" \"c\" f\"d\"",
            expected_constants: &[("ab", 1, 2), ("cd", 1, 13)],
        },
        JoinedConstantTestCase {
            description: "an empty plain string starts a run and an empty f-string does not",
            source: "x = [\"\" f\"a{x}\", f\"{x}\" f\"\" \"b\"]",
            expected_constants: &[("a", 1, 5), ("b", 1, 28)],
        },
        JoinedConstantTestCase {
            description: "format specs are walked one level deeper",
            source: "f\"{x:>{y}d}\" \"\\u00e9\"",
            expected_constants: &[("é", 1, 13), (">", 1, 5), ("d", 1, 9)],
        },
        JoinedConstantTestCase {
            description: "lines end at carriage returns",
            source: "x = 1\r\ny = f\"\"\"a\r{x}\"\"\"",
            expected_constants: &[("a\n", 2, 8)],
        },
    ];
    for test_case in test_cases {
        let parsed: Option<ParsedSource> = parse_cpython_module(test_case.source, (3, 12));
        let statements: Vec<CpythonNode<'_>> = parsed
            .iter()
            .flat_map(|parsed| parsed.module.body.iter().map(CpythonNode::Stmt))
            .collect();
        let constants: Vec<(String, usize, usize)> = walk_breadth_first(statements)
            .into_iter()
            .filter_map(|node| {
                let CpythonNode::Text(constant) = node else {
                    return None;
                };
                let (line, column) = parsed.as_ref().map_or((0, 0), |parsed| {
                    source_position(&parsed.lines, constant.start)
                });
                Some((constant.value, line, column))
            })
            .collect();
        let found: Vec<(&str, usize, usize)> = constants
            .iter()
            .map(|(value, line, column)| (value.as_str(), *line, *column))
            .collect();
        assert_eq!(
            found, test_case.expected_constants,
            "{}",
            test_case.description
        );
    }
}
