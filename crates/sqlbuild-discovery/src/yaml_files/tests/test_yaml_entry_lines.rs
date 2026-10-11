use crate::yaml_files::main::yaml_entry_lines::yaml_entry_lines;
use crate::yaml_files::tests::test_types::EntryLinesTestCase;

#[test]
fn given_yaml_declarations_when_indexing_entries_then_lines_match_the_python_scanner() {
    let test_cases = [
        EntryLinesTestCase {
            description: "the least-indented entry wins and keeps its value's leading space variant",
            contents: "  - name: x\n- name: y\n - name: x",
            expected_lines: &[("x", Some(3)), (" x", Some(3)), ("y", Some(2)), ("z", None)],
        },
        EntryLinesTestCase {
            description: "equal indents keep the first line",
            contents: "- name: orders\n- name: orders\n",
            expected_lines: &[("orders", Some(1))],
        },
        EntryLinesTestCase {
            description: "quotes, comments and non-ASCII names on later lines",
            contents: "  - name: 'it''s'  # note\n- name: \"caf\u{e9}\" # x",
            expected_lines: &[
                ("it''s", Some(1)),
                ("caf\u{e9}", Some(2)),
                ("\"caf\u{e9}\" # x", Some(2)),
            ],
        },
        EntryLinesTestCase {
            description: "CRLF and non-breaking-space indents count Unicode whitespace",
            contents: "\u{a0}- name:orders\r\n-name: orders",
            expected_lines: &[("orders", Some(2)), (" orders", Some(2))],
        },
        EntryLinesTestCase {
            description: "every hash starts a possible comment",
            contents: "- name: a#b\n",
            expected_lines: &[("a", Some(1)), ("a#b", Some(1))],
        },
        EntryLinesTestCase {
            description: "a key without a colon is not an entry and an empty value names nothing",
            contents: "- name\n- name: \n",
            expected_lines: &[("", Some(2)), (" ", Some(2)), ("name", None)],
        },
    ];
    for test_case in test_cases {
        let lines: Vec<(String, usize)> = yaml_entry_lines(test_case.contents);

        let found: Vec<(&str, Option<usize>)> = test_case
            .expected_lines
            .iter()
            .map(|(name, _)| {
                let line: Option<usize> = lines
                    .iter()
                    .find(|(entry, _)| entry == name)
                    .map(|(_, line)| *line);
                (*name, line)
            })
            .collect();
        assert_eq!(found, test_case.expected_lines, "{}", test_case.description);
    }
}
