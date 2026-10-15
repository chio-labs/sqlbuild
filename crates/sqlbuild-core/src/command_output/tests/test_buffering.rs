use crate::command_output::main::append_output::append_output;
use crate::command_output::main::close_output::close_output;
use crate::command_output::models::{OutputBuffer, OutputStream};
use crate::command_output::tests::test_types::BufferingTestCase;

#[test]
fn given_fragments_when_appending_and_closing_then_lines_coalesce_within_the_record_limit() {
    let test_cases = [
        BufferingTestCase {
            description: "small lines coalesce into one record at close",
            max_record_bytes: 64,
            fragments: &["one\ntw", "o\nthree"],
            expected_messages: &["one\ntwo\nthree"],
            expected_partial: "",
        },
        BufferingTestCase {
            description: "a line wider than the limit is split into its own chunks",
            max_record_bytes: 4,
            fragments: &["ab\n", "abcdefgh\n"],
            expected_messages: &["ab\n", "abcd", "efgh", "\n"],
            expected_partial: "",
        },
    ];

    for test_case in test_cases {
        let mut buffer = OutputBuffer::new(test_case.max_record_bytes);
        let mut messages: Vec<String> = Vec::new();
        for fragment in test_case.fragments {
            let outcome = append_output(buffer, (OutputStream::Stdout, fragment.as_bytes()), 0.0);
            buffer = outcome.buffer;
            messages.extend(
                outcome
                    .drafts
                    .iter()
                    .map(|draft| String::from_utf8_lossy(&draft.message).into_owned()),
            );
        }
        let closed = close_output(buffer, 1.0);
        messages.extend(
            closed
                .drafts
                .iter()
                .map(|draft| String::from_utf8_lossy(&draft.message).into_owned()),
        );

        assert_eq!(
            (
                messages,
                String::from_utf8_lossy(&closed.buffer.partials[0]).into_owned()
            ),
            (
                test_case
                    .expected_messages
                    .iter()
                    .map(|message| (*message).to_owned())
                    .collect::<Vec<String>>(),
                test_case.expected_partial.to_owned()
            ),
            "{}",
            test_case.description
        );
    }
}
